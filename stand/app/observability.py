"""Fail-open Langfuse helpers for red-team requests entering the stand."""

import os
import re
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Mapping


_active: ContextVar[bool] = ContextVar("redteam_trace_active", default=False)
_SENSITIVE = re.compile(
    r"authorization|cookie|api[_-]?key|password|secret|token|credential",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET = re.compile(r"(?<![A-Za-z0-9_])(?:sk|pk)-[A-Za-z0-9_-]{8,}")


class _NoopObservation:
    def update(self, **_values: Any) -> None:
        return None


@lru_cache
def _client():
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not public_key or not secret_key:
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=os.getenv("LANGFUSE_BASE_URL", "http://host.docker.internal:3001"),
            environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "local"),
            sample_rate=1.0,
            timeout=2,
            mask=lambda data, **_kwargs: sanitize(data),
        )
    except Exception:
        return None


@contextmanager
def request_observation(
    headers: Mapping[str, str],
    name: str,
    *,
    user_id: str,
    session_id: str,
    input: Any = None,
):
    """Continue a remote W3C trace; do nothing for ordinary stand traffic."""
    traceparent = next(
        (value for key, value in headers.items() if key.lower() == "traceparent"), None
    )
    client = _client()
    if not traceparent or client is None:
        yield _NoopObservation()
        return
    token = None
    active_token = None
    manager = None
    try:
        from opentelemetry.context import attach, detach
        from opentelemetry.propagate import extract

        token = attach(extract(dict(headers)))
        manager = client.start_as_current_observation(
            name=name,
            as_type="agent",
            input=sanitize(input),
            metadata={
                "component": "target-stand",
                "agent_role": "target",
                "user_id": user_id,
                "session_id": session_id,
            },
        )
        observation = manager.__enter__()
        active_token = _active.set(True)
    except Exception:
        if token is not None:
            try:
                detach(token)
            except Exception:
                pass
        yield _NoopObservation()
        return
    try:
        yield observation
    finally:
        if active_token is not None:
            _active.reset(active_token)
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                pass
        if token is not None:
            try:
                detach(token)
            except Exception:
                pass


def observation(
    name: str,
    *,
    as_type: str = "span",
    input: Any = None,
    metadata: Mapping[str, Any] | None = None,
):
    client = _client()
    if client is None or not _active.get():
        return nullcontext(_NoopObservation())
    try:
        return client.start_as_current_observation(
            name=name,
            as_type=as_type,
            input=sanitize(input),
            metadata=sanitize({"agent_role": "target", **dict(metadata or {})}),
        )
    except Exception:
        return nullcontext(_NoopObservation())


def langchain_config(metadata: Mapping[str, Any] | None = None) -> dict:
    if _client() is None or not _active.get():
        return {}
    try:
        from langfuse.langchain import CallbackHandler

        return {
            "callbacks": [CallbackHandler()],
            "metadata": {
                "langfuse_tags": ["target-stand", "redteam"],
                "agent_role": "target",
                **sanitize(dict(metadata or {})),
            },
        }
    except Exception:
        return {}


def flush() -> None:
    client = _client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass


def sanitize(value: Any, max_chars: int = 4000) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[redacted]"
                if _SENSITIVE.search(str(key))
                else sanitize(item, max_chars=max_chars)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item, max_chars=max_chars) for item in value[:100]]
    if isinstance(value, str):
        text = _SECRET.sub("[redacted]", _BEARER.sub("Bearer [redacted]", value))
        return text if len(text) <= max_chars else text[:max_chars] + "…[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize(str(value), max_chars=max_chars)
