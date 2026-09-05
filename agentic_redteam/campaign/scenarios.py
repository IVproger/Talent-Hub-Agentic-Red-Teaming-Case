"""Scenario catalog on the new predicate dictionary.

A scenario file declares a chain of steps (who speaks, in what order) plus the
payload variants that fill the one step marked ``payload: true``. Everything
target-specific stays in ``params`` and in the profile: this module resolves no
identity, contacts nothing, and knows no field names of any target.

`ScenarioSpec` is the on-disk shape; `to_planned()` hands the runner the
`PlannedScenario` it executes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..assertions.dispatch import ASSERTION_TYPES
from ..errors import PipelineConfigurationError
from .orchestrator import PlannedScenario
from .runner import ScenarioStep, validate_step_references

CATALOG = Path(__file__).resolve().parents[1] / "scenarios"
RESET_POLICIES = ("per_scenario", "per_step", "none")
# Fields dispatch.evaluate reads unconditionally — missing them is a config error.
GOAL_REQUIRED: dict[str, tuple[str, ...]] = {
    "tool_principal_equals": ("value",),
    "memory_write": ("scope",),
    "isolation_violation": ("boundary",),
    "external_callback": ("token",),
    "response_contains": ("value",),
}


def _invalid(message: str) -> None:
    raise PipelineConfigurationError(f"Сценарий: {message}.")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} — ожидается непустая строка")
    return value


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    name: str
    attack_class: str
    standard_refs: list[str]
    description: str
    actor: str
    params: dict[str, Any]
    payloads: list[str]
    steps: list[ScenarioStep]
    goal: list[dict]
    boundary: str | None = None
    reset_policy: str = "per_scenario"

    @classmethod
    def load(cls, path: str | Path) -> ScenarioSpec:
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise PipelineConfigurationError(
                f"Не удалось прочитать YAML-сценарий: {path}."
            ) from exc
        if not isinstance(data, dict):
            _invalid(f"{path} — ожидается YAML-отображение (mapping)")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict) -> ScenarioSpec:
        params = data.get("params", {}) or {}
        if not isinstance(params, dict):
            _invalid("params — ожидается отображение")
        render = _renderer(params)
        steps = []
        for index, raw in enumerate(_list(data.get("steps"), "steps"), start=1):
            if not isinstance(raw, dict):
                _invalid(f"steps[{index}] — ожидается отображение")
            if "auth_mode" in raw:
                _invalid(
                    f"шаг '{raw.get('name', index)}' содержит auth_mode — "
                    "режим задаётся кампанией, а не сценарием"
                )
            steps.append(ScenarioStep(
                name=_text(raw.get("name"), f"steps[{index}].name"),
                actor=_text(raw.get("actor"), f"steps[{index}].actor"),
                message=render(raw["message"], f"шаг '{raw.get('name')}'") if raw.get("message") is not None else None,
                payload=bool(raw.get("payload", False)),
                commit_memory=bool(raw.get("commit_memory", False)),
                boundary=raw.get("boundary"),
            ))
        goal = [
            {key: (render(value, f"цель {index}, поле '{key}'") if isinstance(value, str) else value)
             for key, value in _mapping(raw, f"goal[{index}]").items()}
            for index, raw in enumerate(_list(data.get("goal", []), "goal"), start=1)
        ]
        spec = cls(
            id=_text(data.get("id"), "id"),
            name=data.get("name") or data.get("id", ""),
            attack_class=_text(data.get("attack_class"), "attack_class"),
            standard_refs=data.get("standard_refs", []) or [],
            description=data.get("description", ""),
            actor=data.get("actor") or "attacker",
            params=params,
            payloads=[render(p, f"payload {i}") for i, p in
                      enumerate(_list(data.get("payloads", []), "payloads"), start=1)],
            steps=steps,
            goal=goal,
            boundary=data.get("boundary"),
            reset_policy=data.get("reset_policy", "per_scenario"),
        )
        spec.validate()
        return spec

    def validate(self) -> None:
        if self.reset_policy not in RESET_POLICIES:
            _invalid("reset_policy — допустимо: " + ", ".join(RESET_POLICIES))
        for label, value in (("standard_refs", self.standard_refs), ("payloads", self.payloads)):
            for item in _list(value, label):
                _text(item, label)
        if not self.steps:
            _invalid("steps — нужен хотя бы один шаг")
        names: set[str] = set()
        for step in self.steps:
            if step.name in names:
                _invalid(f"имя шага '{step.name}' повторяется")
            names.add(step.name)
            if sum((step.message is not None, step.payload, step.commit_memory)) != 1:
                _invalid(
                    f"шаг '{step.name}' — нужно ровно одно из: message, "
                    "payload: true, commit_memory: true"
                )
        carriers = [step.name for step in self.steps if step.payload]
        if len(carriers) > 1:
            _invalid(f"payload несут несколько шагов: {', '.join(carriers)}")
        if carriers and not self.payloads:
            _invalid(f"шаг '{carriers[0]}' несёт payload, но список payloads пуст")
        if self.payloads and not carriers:
            _invalid("payloads заданы, но ни один шаг не помечен payload: true")
        for index, assertion in enumerate(self.goal, start=1):
            kind = assertion.get("type")
            if kind not in ASSERTION_TYPES:
                _invalid(f"цель {index} — неизвестный предикат '{kind}'")
            missing = [f for f in GOAL_REQUIRED.get(kind, ()) if f not in assertion]
            if missing:
                _invalid(f"цель {index} ({kind}) — не хватает полей: {', '.join(missing)}")
        try:
            validate_step_references(self.goal, self.steps)
        except ValueError as exc:
            _invalid(str(exc))

    def to_planned(self, principals: dict[str, str] | None = None) -> PlannedScenario:
        """Freeze the spec into the runner's plan.

        `principals` maps a role name to the principal value the predicates
        compare against; without it the role name is carried through unchanged.
        """
        return PlannedScenario(
            id=self.id,
            attack_class=self.attack_class,
            standard_refs=list(self.standard_refs),
            actor=(principals or {}).get(self.actor, self.actor),
            payloads=list(self.payloads),
            goal=[dict(assertion) for assertion in self.goal],
            boundary=self.boundary,
            reset_policy=self.reset_policy,
            steps=list(self.steps),
        )


def _list(value: object, label: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        _invalid(f"{label} — ожидается список")
    return value


def _mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        _invalid(f"{label} — ожидается отображение")
    return value


def _renderer(params: dict):
    def render(text: str, label: str) -> str:
        if not isinstance(text, str):
            _invalid(f"{label} — ожидается строка")
        try:
            return text.format(**params)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            _invalid(f"{label} — неразрешимый placeholder: {exc}")
    return render


def load_catalog(root: str | Path | None = None) -> dict[str, ScenarioSpec]:
    """Load every bundled scenario, keyed by id."""
    catalog: dict[str, ScenarioSpec] = {}
    for path in sorted(Path(root or CATALOG).glob("*.yaml")):
        spec = ScenarioSpec.load(path)
        if spec.id in catalog:
            _invalid(f"дублирующийся id '{spec.id}'")
        catalog[spec.id] = spec
    return catalog


def resolve(refs: list[str], root: str | Path | None = None) -> list[ScenarioSpec]:
    """Resolve ids, file paths, or `all` to specs, preserving the given order."""
    catalog = load_catalog(root)
    if not refs or refs == ["all"]:
        return list(catalog.values())
    resolved: dict[str, ScenarioSpec] = {}
    for ref in refs:
        if ref == "all":
            resolved.update(catalog)
            continue
        path = Path(ref)
        spec = ScenarioSpec.load(path) if path.is_file() else catalog.get(ref)
        if spec is None:
            _invalid(f"неизвестный сценарий '{ref}'; доступны: " + ", ".join(sorted(catalog)))
        resolved.setdefault(spec.id, spec)
    return list(resolved.values())
