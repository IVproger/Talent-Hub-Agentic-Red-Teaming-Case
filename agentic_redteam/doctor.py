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
            "Stand source directory is available."
            if stand_ready
            else "Stand source directory is incomplete or missing.",
        ),
    ]
    llm_valid = True
    try:
        validate_role_configs(roles, credential_roles=provider_roles)
        if roles["target_agent"].normalized().temperature != 0:
            raise ValueError(
                "target_agent.temperature is not supported by the current stand; use 0."
            )
        results.append(CheckResult("llm_config", True, "All LLM roles are configured."))
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
            "Docker executable is available."
            if docker_ok
            else "Docker was not found on PATH.",
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
            "Docker Compose is available."
            if compose_ok
            else "Docker Compose is unavailable. Install or enable the Compose plugin.",
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
                "Target agent API URL is invalid or contains a query/fragment.",
            )
        )
    elif target_parts.username is not None or target_parts.password is not None:
        results.append(
            CheckResult(
                "agent_api",
                False,
                "Target agent API URL must not contain credentials.",
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
                    "Target agent API is healthy."
                    if ok
                    else "Target agent API returned an unexpected response.",
                )
            )
        except (OSError, ValueError, urllib.error.URLError):
            results.append(
                CheckResult(
                    "agent_api",
                    False,
                    f"Target agent API is not reachable at {endpoint}.",
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
                    f"Target uses {state.research_model} at {state.base_url}.",
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
                return False, "openrouter rejected its configured credential."
            return False, (
                "openrouter credential check returned "
                f"HTTP {exc.code} at {credential_request.full_url}."
            )
        except (OSError, ValueError, urllib.error.URLError):
            return False, (
                "openrouter credential endpoint is not reachable at "
                f"{credential_request.full_url}."
            )
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code in (401, 403):
            return False, f"{cfg.provider} rejected its configured credential."
        return False, f"{cfg.provider} model check returned HTTP {exc.code} at {url}."
    except (OSError, ValueError, urllib.error.URLError):
        return False, f"{cfg.provider} model endpoint is not reachable at {url}."

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
        return False, f"Model {cfg.model} is not available from {cfg.provider}."
    return True, f"Model {cfg.model} is available from {cfg.provider}."
