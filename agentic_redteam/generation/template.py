"""Templates: пункт стандарта как target-независимая абстракция."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..assertions.dispatch import ASSERTION_TYPES
from ..errors import PipelineConfigurationError


def _invalid(message: str) -> None:
    raise PipelineConfigurationError(f"Шаблон: {message}.")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} — ожидается непустая строка")
    return value


def _list(value: object, label: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        _invalid(f"{label} — ожидается список")
    return value


@dataclass(frozen=True)
class Template:
    id: str
    standard: dict
    title: str
    boundary: str | None
    delivery: list[str]
    requires_features: list[str]
    requires_evidence: list[str]
    enhanced_by: list[str]
    steps: list[dict]
    success: list[dict]
    remediation: str

    @classmethod
    def load(cls, path: str | Path) -> "Template":
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise PipelineConfigurationError(f"Не удалось прочитать шаблон: {path}.") from exc
        if not isinstance(data, dict):
            _invalid(f"{path} — ожидается YAML-отображение")
        pre = data.get("preconditions", {}) or {}
        standard = data.get("standard", {}) or {}
        if not any(standard.get(k) for k in ("asi", "llm", "atlas")):
            _invalid("standard — нужна хотя бы одна ссылка asi/llm/atlas")
        steps = _list(data.get("steps"), "steps")
        if not steps:
            _invalid("steps — нужен хотя бы один шаг")
        success = _list(data.get("success"), "success")
        for item in success:
            if not isinstance(item, dict) or item.get("assert") not in ASSERTION_TYPES:
                _invalid(f"success — неизвестный предикат {item.get('assert') if isinstance(item, dict) else item!r}")
        template = cls(
            id=_text(data.get("id"), "id"),
            standard=standard,
            title=data.get("title", data.get("id", "")),
            boundary=data.get("boundary"),
            delivery=_list(data.get("delivery"), "delivery"),
            requires_features=_list(pre.get("requires_features"), "requires_features"),
            requires_evidence=_list(pre.get("requires_evidence"), "requires_evidence"),
            enhanced_by=_list(pre.get("enhanced_by"), "enhanced_by"),
            steps=[dict(step) for step in steps],
            success=[dict(item) for item in success],
            remediation=data.get("remediation", ""),
        )
        return template


def load_templates(root: str | Path) -> list[Template]:
    return sorted((Template.load(path) for path in Path(root).rglob("*.yaml")),
                  key=lambda t: t.id)
