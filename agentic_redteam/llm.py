"""Provider-neutral LLM configuration and HTTP clients.

The red-team pipeline has three distinct LLM roles.  Keeping their configuration
separate makes mixed experiments explicit and prevents a model choice in one stage
from leaking into another one.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Callable, Mapping, Protocol


ROLE_NAMES = ("attack_generator", "report_writer", "analyst")
PROVIDERS = ("ollama", "openrouter")
SECRET_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])"
)


class LLMConfigurationError(ValueError):
    """The selected provider/model cannot be used safely."""


class LLMRequestError(RuntimeError):
    """A provider request failed with a user-actionable error."""


@dataclass(frozen=True)
class LLMRoleConfig:
    provider: str = "ollama"
    model: str = "qwen3:8b"
    base_url: str | None = None
    api_key_env: str | None = None
    temperature: float = 0.0
    timeout: int = 600

    def normalized(self) -> "LLMRoleConfig":
        if not isinstance(self.provider, str):
            raise LLMConfigurationError("provider must be a string.")
        if not isinstance(self.model, str):
            raise LLMConfigurationError("model must be a string.")
        if self.base_url is not None and not isinstance(self.base_url, str):
            raise LLMConfigurationError("base_url must be a string.")
        if self.api_key_env is not None and not isinstance(self.api_key_env, str):
            raise LLMConfigurationError("api_key_env must be a string.")
        try:
            temperature = float(self.temperature)
            timeout = int(self.timeout)
        except (TypeError, ValueError) as exc:
            raise LLMConfigurationError(
                "temperature must be numeric and timeout must be an integer."
            ) from exc
        provider = self.provider.strip().lower()
        model = self.model.strip()
        base_url = (self.base_url or default_base_url(provider)).rstrip("/")
        api_key_env = self.api_key_env or (
            "OPENROUTER_API_KEY" if provider == "openrouter" else None
        )
        return LLMRoleConfig(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            temperature=temperature,
            timeout=timeout,
        )

    def validate(
        self,
        environ: Mapping[str, str] | None = None,
        *,
        require_credentials: bool = True,
    ) -> None:
        cfg = self.normalized()
        if cfg.provider not in PROVIDERS:
            raise LLMConfigurationError(
                f"Unknown LLM provider '{cfg.provider}'. Choose: {', '.join(PROVIDERS)}."
            )
        if not cfg.model:
            raise LLMConfigurationError("LLM model cannot be empty.")
        if cfg.provider == "openrouter" and "/" not in cfg.model:
            raise LLMConfigurationError(
                "OpenRouter model must use its full identifier, for example "
                "'openai/gpt-5-mini'."
            )
        if not cfg.base_url or not cfg.base_url.startswith(("http://", "https://")):
            raise LLMConfigurationError("LLM base_url must start with http:// or https://.")
        try:
            parsed_url = urllib.parse.urlsplit(cfg.base_url)
            parsed_port = parsed_url.port
        except ValueError as exc:
            raise LLMConfigurationError("LLM base_url is not a valid URL.") from exc
        if (
            not parsed_url.hostname
            or parsed_port is None and ":" in parsed_url.netloc.rsplit("]", 1)[-1]
        ):
            raise LLMConfigurationError("LLM base_url is not a valid URL.")
        if parsed_url.username is not None or parsed_url.password is not None:
            raise LLMConfigurationError(
                "LLM base_url must not contain credentials; use an environment variable."
            )
        if parsed_url.query or parsed_url.fragment:
            raise LLMConfigurationError(
                "LLM base_url must not contain a query string or fragment."
            )
        if cfg.api_key_env and not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", cfg.api_key_env
        ):
            raise LLMConfigurationError(
                "api_key_env must be a valid environment variable name."
            )
        if not 0 <= cfg.temperature <= 2:
            raise LLMConfigurationError("LLM temperature must be between 0 and 2.")
        if cfg.timeout <= 0:
            raise LLMConfigurationError("LLM timeout must be greater than zero.")
        env = os.environ if environ is None else environ
        if (
            require_credentials
            and cfg.provider == "openrouter"
            and not env.get(cfg.api_key_env or "")
        ):
            raise LLMConfigurationError(
                f"OpenRouter is selected but {cfg.api_key_env} is not set. "
                "Export the key before starting the run."
            )

    def safe_dict(self) -> dict:
        """Return serializable configuration without secret values."""
        return asdict(self.normalized())


def default_base_url(provider: str) -> str:
    if provider.strip().lower() == "openrouter":
        return "https://openrouter.ai/api/v1"
    return "http://localhost:11434"


def default_role_configs() -> dict[str, LLMRoleConfig]:
    return {role: LLMRoleConfig() for role in ROLE_NAMES}


def role_configs_from_mapping(data: Mapping | None) -> dict[str, LLMRoleConfig]:
    """Merge a YAML-compatible mapping over safe Ollama defaults."""
    result = default_role_configs()
    if data is not None and not isinstance(data, Mapping):
        raise LLMConfigurationError("llm configuration must be a mapping.")
    for role, raw in (data or {}).items():
        if role not in ROLE_NAMES:
            raise LLMConfigurationError(
                f"Unknown LLM role '{role}'. Choose: {', '.join(ROLE_NAMES)}."
            )
        if not isinstance(raw, Mapping):
            raise LLMConfigurationError(f"Configuration for {role} must be a mapping.")
        unknown = set(raw) - set(LLMRoleConfig.__dataclass_fields__)
        if unknown:
            raise LLMConfigurationError(
                f"Unknown fields for {role}: {', '.join(sorted(unknown))}."
            )
        current = result[role].safe_dict()
        incoming_provider = raw.get("provider", current["provider"])
        if not isinstance(incoming_provider, str):
            raise LLMConfigurationError(f"{role}: provider must be a string.")
        incoming_provider = incoming_provider.strip().lower()
        if incoming_provider != current["provider"]:
            if "base_url" not in raw:
                current["base_url"] = None
            if "api_key_env" not in raw:
                current["api_key_env"] = None
        current.update(dict(raw))
        try:
            result[role] = LLMRoleConfig(**current).normalized()
        except LLMConfigurationError as exc:
            raise LLMConfigurationError(f"{role}: {exc}") from exc
    return result


def validate_role_configs(
    configs: Mapping[str, LLMRoleConfig],
    environ: Mapping[str, str] | None = None,
    *,
    credential_roles: tuple[str, ...] = ("attack_generator", "report_writer"),
) -> None:
    unknown = set(configs) - set(ROLE_NAMES)
    if unknown:
        raise LLMConfigurationError(f"Unknown LLM roles: {', '.join(sorted(unknown))}.")
    missing = [role for role in ROLE_NAMES if role not in configs]
    if missing:
        raise LLMConfigurationError(f"Missing LLM roles: {', '.join(missing)}.")
    for role in ROLE_NAMES:
        try:
            configs[role].validate(environ, require_credentials=role in credential_roles)
        except LLMConfigurationError as exc:
            raise LLMConfigurationError(f"{role}: {exc}") from exc


def apply_role_overrides(
    configs: Mapping[str, LLMRoleConfig],
    overrides: Mapping[str, Mapping[str, object]],
) -> dict[str, LLMRoleConfig]:
    result = {role: cfg.normalized() for role, cfg in configs.items()}
    for role, values in overrides.items():
        if role not in ROLE_NAMES:
            raise LLMConfigurationError(f"Unknown LLM role '{role}'.")
        merged = result[role].safe_dict()
        incoming_provider = values.get("provider")
        if incoming_provider is not None and str(incoming_provider).strip().lower() != merged["provider"]:
            if values.get("base_url") is None:
                merged["base_url"] = None
            if values.get("api_key_env") is None:
                merged["api_key_env"] = None
        merged.update({key: value for key, value in values.items() if value is not None})
        result[role] = LLMRoleConfig(**merged).normalized()
    return result


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


Transport = Callable[[urllib.request.Request, int], dict]


def _default_transport(request: urllib.request.Request, timeout: int) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            detail = "authentication was rejected"
        elif exc.code == 429:
            detail = "rate limit was reached"
        else:
            detail = f"provider returned HTTP {exc.code}"
        provider_message = _http_error_message(exc)
        exc.close()
        suffix = f" Provider detail: {provider_message}." if provider_message else ""
        raise LLMRequestError(f"LLM request failed: {detail}.{suffix}") from exc
    except urllib.error.URLError as exc:
        raise LLMRequestError(
            "LLM provider could not be reached. Check its URL and network connection."
        ) from exc
    except TimeoutError as exc:
        raise LLMRequestError("LLM request timed out.") from exc


class HTTPChatClient:
    def __init__(
        self,
        config: LLMRoleConfig,
        *,
        environ: Mapping[str, str] | None = None,
        transport: Transport | None = None,
    ):
        self.config = config.normalized()
        self.environ = os.environ if environ is None else environ
        self.config.validate(self.environ)
        self._transport = transport or _default_transport
        self.last_usage: dict[str, int] | None = None

    def complete(self, prompt: str) -> str:
        if self.config.provider == "ollama":
            payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": self.config.temperature},
            }
            url = _endpoint(self.config.base_url or "", "/api/chat", "/api/chat")
            headers = {"Content-Type": "application/json"}
        else:
            payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.config.temperature,
            }
            url = _endpoint(
                self.config.base_url or "", "/chat/completions", "/chat/completions"
            )
            key = self.environ[self.config.api_key_env or "OPENROUTER_API_KEY"]
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )
        try:
            response = self._transport(request, self.config.timeout)
            if self.config.provider == "ollama":
                text = response["message"]["content"]
                self.last_usage = _usage_details(
                    response.get("prompt_eval_count"), response.get("eval_count")
                )
            else:
                text = response["choices"][0]["message"]["content"]
                usage = response.get("usage") or {}
                self.last_usage = _usage_details(
                    usage.get("prompt_tokens"), usage.get("completion_tokens")
                )
        except LLMRequestError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMRequestError("LLM provider returned an invalid response.") from exc
        if not isinstance(text, str) or not text.strip():
            raise LLMRequestError("LLM provider returned an empty response.")
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _endpoint(base_url: str, suffix: str, already_suffix: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith(already_suffix) else base + suffix


def make_llm_client(
    config: LLMRoleConfig,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> HTTPChatClient:
    return HTTPChatClient(config, environ=environ, transport=transport)


def _usage_details(input_tokens, output_tokens) -> dict[str, int] | None:
    if not isinstance(input_tokens, int) and not isinstance(output_tokens, int):
        return None
    values = {
        "input": input_tokens if isinstance(input_tokens, int) else 0,
        "output": output_tokens if isinstance(output_tokens, int) else 0,
    }
    values["total"] = values["input"] + values["output"]
    return values


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    """Extract a short provider diagnostic without reflecting credentials."""
    try:
        body = exc.read(4096).decode("utf-8", errors="replace")
    except Exception:
        return ""
    try:
        parsed = json.loads(body)
        candidate = parsed.get("error", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(candidate, dict):
            candidate = candidate.get("message") or candidate.get("detail")
        message = candidate if isinstance(candidate, str) else body
    except json.JSONDecodeError:
        message = body
    return " ".join(redact_credential_tokens(message).split())[:500]


def redact_credential_tokens(text: str) -> str:
    """Redact common bearer and ``sk-`` credentials without matching word fragments."""
    text = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [redacted]",
        text,
    )
    return SECRET_TOKEN_PATTERN.sub("[redacted]", text)
