"""Optional, fail-open Langfuse tracing for red-team pipeline runs."""
from __future__ import annotations

import os
import re
import sys
import threading
import urllib.parse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Mapping


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SENSITIVE_KEY = re.compile(
    r"authorization|cookie|api[_-]?key|password|secret|token|credential",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET = re.compile(r"(?<![A-Za-z0-9_])(?:sk|pk)-[A-Za-z0-9_-]{8,}")


class ObservabilityConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class LangfuseConfig:
    enabled: bool = False
    host: str = "http://localhost:3001"
    project_id: str = "agentic-redteam"
    environment: str = "local"
    public_key_env: str = "LANGFUSE_PUBLIC_KEY"
    secret_key_env: str = "LANGFUSE_SECRET_KEY"
    capture: str = "redacted"
    max_value_chars: int = 4000
    flush_timeout_seconds: float = 3.0

    def validate(self) -> "LangfuseConfig":
        if not isinstance(self.enabled, bool):
            raise ObservabilityConfigurationError("langfuse.enabled must be boolean.")
        for name in ("host", "project_id", "environment", "capture"):
            if not isinstance(getattr(self, name), str):
                raise ObservabilityConfigurationError(f"langfuse.{name} must be a string.")
        parsed = urllib.parse.urlsplit(self.host)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ObservabilityConfigurationError(
                "langfuse.host must be an http(s) URL without credentials, query, or fragment."
            )
        if not self.project_id.strip():
            raise ObservabilityConfigurationError("langfuse.project_id cannot be empty.")
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", self.environment):
            raise ObservabilityConfigurationError(
                "langfuse.environment must use lowercase letters, numbers, '-' or '_'."
            )
        if self.capture not in ("redacted", "metadata-only"):
            raise ObservabilityConfigurationError(
                "langfuse.capture must be 'redacted' or 'metadata-only'."
            )
        for name in ("public_key_env", "secret_key_env"):
            if not _ENV_NAME.fullmatch(getattr(self, name)):
                raise ObservabilityConfigurationError(
                    f"langfuse.{name} must be a valid environment variable name."
                )
        if not isinstance(self.max_value_chars, int) or not 128 <= self.max_value_chars <= 100_000:
            raise ObservabilityConfigurationError(
                "langfuse.max_value_chars must be between 128 and 100000."
            )
        if not isinstance(self.flush_timeout_seconds, (int, float)) or not 0 < float(
            self.flush_timeout_seconds
        ) <= 30:
            raise ObservabilityConfigurationError(
                "langfuse.flush_timeout_seconds must be between 0 and 30."
            )
        return self

    def safe_dict(self) -> dict:
        return asdict(self)


def langfuse_config_from_mapping(data: Mapping | None) -> LangfuseConfig:
    if data is None:
        return LangfuseConfig()
    if not isinstance(data, Mapping):
        raise ObservabilityConfigurationError("observability must be a mapping.")
    raw = data.get("langfuse", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ObservabilityConfigurationError("observability.langfuse must be a mapping.")
    unknown = set(raw) - set(LangfuseConfig.__dataclass_fields__)
    if unknown:
        raise ObservabilityConfigurationError(
            "Unknown observability.langfuse fields: " + ", ".join(sorted(unknown))
        )
    try:
        return LangfuseConfig(**dict(raw)).validate()
    except TypeError as exc:
        raise ObservabilityConfigurationError(f"Invalid Langfuse configuration: {exc}") from exc


class NoopObservation:
    trace_id: str | None = None
    id: str | None = None

    def update(self, **_values: Any) -> None:
        return None


class LangfuseTelemetry:
    """Small SDK boundary so observability can never own pipeline correctness."""

    def __init__(
        self,
        config: LangfuseConfig,
        *,
        environ: Mapping[str, str] | None = None,
        client: Any | None = None,
    ):
        self.config = config.validate()
        self.environ = os.environ if environ is None else environ
        self.client = None
        self.warning: str | None = None
        self.trace_id: str | None = None
        self.trace_url: str | None = None
        self.root_observation_id: str | None = None
        if not config.enabled:
            return
        public_key = self.environ.get(config.public_key_env, "")
        secret_key = self.environ.get(config.secret_key_env, "")
        if not public_key or not secret_key:
            self.warning = (
                "Langfuse tracing is enabled but its configured credentials are missing."
            )
            return
        try:
            if client is None:
                from langfuse import Langfuse

                client = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    base_url=config.host.rstrip("/"),
                    environment=config.environment,
                    sample_rate=1.0,
                    timeout=2,
                    mask=lambda data, **_kwargs: sanitize_trace_value(
                        data, max_chars=config.max_value_chars
                    ),
                )
            self.client = client
        except Exception as exc:
            self.warning = f"Langfuse initialization failed: {type(exc).__name__}."

    @property
    def active(self) -> bool:
        return self.client is not None

    @contextmanager
    def run(
        self,
        run_id: str,
        *,
        metadata: Mapping[str, Any],
        input: Any | None = None,
    ) -> Iterator[Any]:
        if self.client is None:
            yield NoopObservation()
            return
        try:
            trace_id = self.client.create_trace_id(seed=run_id)
            safe_input = self._capture(input)
            manager = self.client.start_as_current_observation(
                name="redteam.run",
                as_type="agent",
                trace_context={"trace_id": trace_id},
                input=safe_input,
                metadata=sanitize_trace_value(
                    dict(metadata), max_chars=self.config.max_value_chars
                ),
            )
            observation = manager.__enter__()
        except Exception as exc:
            self.warning = f"Langfuse tracing failed: {type(exc).__name__}."
            yield NoopObservation()
            return
        self.trace_id = str(observation.trace_id)
        self.root_observation_id = str(observation.id)
        self.trace_url = (
            f"{self.config.host.rstrip('/')}/project/"
            f"{urllib.parse.quote(self.config.project_id, safe='')}/traces/"
            f"{self.trace_id}"
        )
        try:
            yield observation
        except BaseException:
            suppress = manager.__exit__(*sys.exc_info())
            if not suppress:
                raise
        else:
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:
                self.warning = f"Langfuse tracing close failed: {type(exc).__name__}."

    @contextmanager
    def observation(
        self,
        name: str,
        *,
        as_type: str = "span",
        input: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
        model: str | None = None,
    ) -> Iterator[Any]:
        if self.client is None:
            yield NoopObservation()
            return
        try:
            manager = self.client.start_as_current_observation(
                name=name,
                as_type=as_type,
                input=self._capture(input),
                metadata=sanitize_trace_value(
                    dict(metadata or {}), max_chars=self.config.max_value_chars
                ),
                model=model,
            )
            observation = manager.__enter__()
        except Exception as exc:
            self.warning = f"Langfuse observation failed: {type(exc).__name__}."
            yield NoopObservation()
            return
        try:
            yield observation
        except BaseException:
            suppress = manager.__exit__(*sys.exc_info())
            if not suppress:
                raise
        else:
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:
                self.warning = f"Langfuse observation close failed: {type(exc).__name__}."

    def propagation_headers(self) -> dict[str, str]:
        if self.client is None:
            return {}
        try:
            from opentelemetry.propagate import inject

            carrier: dict[str, str] = {}
            inject(carrier)
            return {
                key: value
                for key, value in carrier.items()
                if key.lower() in ("traceparent", "tracestate", "baggage")
            }
        except Exception as exc:
            self.warning = f"Trace propagation failed: {type(exc).__name__}."
            return {}

    def score_attempt(self, observation_id: str | None, verdict: str) -> None:
        if self.client is None or not self.trace_id:
            return
        try:
            self.client.create_score(
                name="verdict",
                value=verdict,
                data_type="CATEGORICAL",
                trace_id=self.trace_id,
                observation_id=observation_id,
                environment=self.config.environment,
            )
            self.client.create_score(
                name="attack_success",
                value=1.0 if verdict == "proven" else 0.0,
                data_type="BOOLEAN",
                trace_id=self.trace_id,
                observation_id=observation_id,
                environment=self.config.environment,
            )
        except Exception as exc:
            self.warning = f"Langfuse score export failed: {type(exc).__name__}."

    def score_run(self, asr_percent: float) -> None:
        if self.client is None or not self.trace_id:
            return
        try:
            self.client.create_score(
                name="asr_percent",
                value=float(asr_percent),
                data_type="NUMERIC",
                trace_id=self.trace_id,
                environment=self.config.environment,
            )
        except Exception as exc:
            self.warning = f"Langfuse score export failed: {type(exc).__name__}."

    def flush(self) -> None:
        if self.client is None:
            return
        error: list[Exception] = []

        def execute() -> None:
            try:
                self.client.flush()
            except Exception as exc:  # pragma: no cover - SDK is documented fail-open
                error.append(exc)

        worker = threading.Thread(target=execute, daemon=True, name="langfuse-flush")
        worker.start()
        worker.join(float(self.config.flush_timeout_seconds))
        if worker.is_alive():
            self.warning = "Langfuse flush exceeded its configured timeout."
        elif error:
            self.warning = f"Langfuse flush failed: {type(error[0]).__name__}."

    def _capture(self, value: Any) -> Any:
        if self.config.capture == "metadata-only":
            return None
        return sanitize_trace_value(value, max_chars=self.config.max_value_chars)


def sanitize_trace_value(value: Any, *, max_chars: int = 4000) -> Any:
    """Redact secrets recursively and bound values before they enter telemetry."""
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[redacted]"
                if _SENSITIVE_KEY.search(str(key))
                else sanitize_trace_value(item, max_chars=max_chars)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_trace_value(item, max_chars=max_chars) for item in value[:100]]
    if isinstance(value, str):
        redacted = _SECRET.sub("[redacted]", _BEARER.sub("Bearer [redacted]", value))
        if len(redacted) > max_chars:
            return redacted[:max_chars] + "…[truncated]"
        return redacted
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_trace_value(str(value), max_chars=max_chars)
