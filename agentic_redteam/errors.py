"""Ошибки ядра и приведение их текста к безопасному для показа виду."""
from __future__ import annotations

import os
import re

from .llm import redact_credential_tokens


class PipelineConfigurationError(ValueError):
    """The supplied configuration cannot be used to execute a campaign."""


def redact_secrets(text: str) -> str:
    """Redact credential-shaped and configured secret values from persisted text."""
    text = re.sub(
        r"(?i)((?:\"authorization\"|'authorization'|authorization)\s*[:=]\s*)"
        r"([\"'])(.*?)\2",
        r"\1\2[redacted]\2",
        text,
    )
    text = re.sub(
        r"(?im)(\bauthorization\b\s*[:=]\s*)[^\r\n,;}]+",
        r"\1[redacted]",
        text,
    )
    text = redact_credential_tokens(text)
    for name, value in os.environ.items():
        if value and any(token in name.upper() for token in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
            text = text.replace(value, "[redacted]")
    return text


def sanitize_error(exc: Exception) -> str:
    """Return an operational error safe to show in CLI/UI and artifacts."""
    text = str(exc).strip() or exc.__class__.__name__
    return redact_secrets(text)[:1000]
