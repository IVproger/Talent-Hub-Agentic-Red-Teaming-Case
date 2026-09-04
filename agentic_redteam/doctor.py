"""Read-only environment checks used by the CLI and local UI."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from . import config as runtime_config
from .llm import LLMRoleConfig, validate_role_configs
from .target_runtime import TargetConfigurationError, TargetRuntime


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    blocking: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def run_checks(
    roles: Mapping[str, LLMRoleConfig],
    *,
    target_api: str | None = None,
    compose_file: str | None = None,
    check_network: bool = True,
    target_runtime: TargetRuntime | None = None,
    provider_probe: Callable[[LLMRoleConfig], tuple[bool, str]] | None = None,
    provider_roles: tuple[str, ...] = ("attack_generator", "report_writer"),
) -> list[CheckResult]:
    compose = Path(compose_file or runtime_config.COMPOSE_FILE)
    stand_dir = compose.parent
    stand_ready = compose.is_file() and (stand_dir / "app" / "api_server.py").is_file()
    results = [
        CheckResult(
            "stand",
            stand_ready,
            "Каталог с исходниками стенда доступен."
            if stand_ready
            else "Каталог с исходниками стенда неполон или отсутствует.",
        ),
    ]
    llm_valid = True
    try:
        validate_role_configs(roles, credential_roles=provider_roles)
        if roles["target_agent"].normalized().temperature != 0:
            raise ValueError(
                "target_agent.temperature is not supported by the current stand; use 0."
            )
        results.append(CheckResult("llm_config", True, "Все LLM-роли настроены."))
    except ValueError as exc:
        llm_valid = False
        results.append(CheckResult("llm_config", False, str(exc)))

    if not check_network:
        return results

    docker_path = shutil.which("docker")
    docker_ok = docker_path is not None
    results.append(
        CheckResult(
            "docker",
            docker_ok,
            "Исполняемый файл Docker доступен."
            if docker_ok
            else "Docker не найден в PATH.",
        )
    )
    compose_ok = False
    if docker_path:
        try:
            compose_result = subprocess.run(
                [docker_path, "compose", "version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            compose_ok = compose_result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            compose_ok = False
    results.append(
        CheckResult(
            "docker_compose",
            compose_ok,
            "Docker Compose доступен."
            if compose_ok
            else "Docker Compose недоступен. Установите или включите плагин Compose.",
        )
    )

    probe = provider_probe or _probe_provider
    if llm_valid:
        for role, selected in roles.items():
            if role not in provider_roles:
                continue
            cfg = selected.normalized()
            ok, message = probe(cfg)
            results.append(CheckResult(f"provider_{role}", ok, message))

    target_base = (target_api or runtime_config.AGENT_API).rstrip("/")
    try:
        target_parts = urllib.parse.urlsplit(target_base)
        target_port = target_parts.port
    except ValueError:
        target_parts = None
        target_port = None
    if (
        target_parts is None
        or target_parts.scheme not in ("http", "https")
        or not target_parts.hostname
        or target_port is None and ":" in target_parts.netloc.rsplit("]", 1)[-1]
        or target_parts.query
        or target_parts.fragment
    ):
        results.append(
            CheckResult(
                "agent_api",
                False,
                "URL целевого agent API некорректен или содержит query/fragment.",
            )
        )
    elif target_parts.username is not None or target_parts.password is not None:
        results.append(
            CheckResult(
                "agent_api",
                False,
                "URL целевого agent API не должен содержать учётные данные.",
            )
        )
    else:
        endpoint = target_base + "/healthz"
        try:
            with urllib.request.urlopen(endpoint, timeout=3) as response:
                body = json.load(response)
            ok = response.status == 200 and body.get("status") == "ok"
            results.append(
                CheckResult(
                    "agent_api",
                    ok,
                    "Целевой agent API работает нормально."
                    if ok
                    else "Целевой agent API вернул неожиданный ответ.",
                )
            )
        except (OSError, ValueError, urllib.error.URLError):
            results.append(
                CheckResult(
                    "agent_api",
                    False,
                    f"Целевой agent API недоступен по адресу {endpoint}.",
                )
            )

    if llm_valid:
        try:
            state = (target_runtime or TargetRuntime(str(compose))).assert_matches(
                roles["target_agent"]
            )
            results.append(
                CheckResult(
                    "target_model",
                    True,
                    f"Цель использует {state.research_model} на {state.base_url}.",
                )
            )
        except (TargetConfigurationError, KeyError) as exc:
            results.append(CheckResult("target_model", False, str(exc)))
    return results


def checks_ok(results: list[CheckResult]) -> bool:
    return all(item.ok or not item.blocking for item in results)


def _probe_provider(config: LLMRoleConfig) -> tuple[bool, str]:
    cfg = config.normalized()
    base = (cfg.base_url or "").rstrip("/")
    headers = {"Accept": "application/json"}
    if cfg.provider == "ollama":
        if base.endswith("/api/chat"):
            base = base[: -len("/api/chat")]
        url = base + "/api/tags"
    else:
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        url = base + "/models"
        key = os.environ.get(cfg.api_key_env or "OPENROUTER_API_KEY", "")
        headers["Authorization"] = f"Bearer {key}"
        credential_request = urllib.request.Request(
            base + "/key", headers=headers, method="GET"
        )
        try:
            with urllib.request.urlopen(credential_request, timeout=3) as response:
                json.load(response)
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code in (401, 403):
                return False, "openrouter отклонил настроенные учётные данные."
            return False, (
                "проверка учётных данных openrouter вернула "
                f"HTTP {exc.code} на {credential_request.full_url}."
            )
        except (OSError, ValueError, urllib.error.URLError):
            return False, (
                "эндпоинт учётных данных openrouter недоступен по адресу "
                f"{credential_request.full_url}."
            )
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code in (401, 403):
            return False, f"{cfg.provider} отклонил настроенные учётные данные."
        return False, f"проверка модели {cfg.provider} вернула HTTP {exc.code} на {url}."
    except (OSError, ValueError, urllib.error.URLError):
        return False, f"эндпоинт модели {cfg.provider} недоступен по адресу {url}."

    if cfg.provider == "ollama":
        models = payload.get("models", []) if isinstance(payload, dict) else []
        identifiers = {
            str(item.get(field))
            for item in models
            if isinstance(item, dict)
            for field in ("name", "model")
            if item.get(field)
        }
        candidates = {cfg.model, f"{cfg.model}:latest"}
    else:
        models = payload.get("data", []) if isinstance(payload, dict) else []
        identifiers = {
            str(item.get("id"))
            for item in models
            if isinstance(item, dict) and item.get("id")
        }
        candidates = {cfg.model}
    if identifiers.isdisjoint(candidates):
        return False, f"Модель {cfg.model} недоступна у провайдера {cfg.provider}."
    return True, f"Модель {cfg.model} доступна у провайдера {cfg.provider}."
