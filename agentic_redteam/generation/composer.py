"""Composer: Template × profile → ScenarioSpec (чистая функция, без сети/LLM)."""
from __future__ import annotations

from dataclasses import dataclass

from ..campaign.scenarios import ScenarioSpec
from ..profile.schema import TargetProfile
from .template import Template

# Имя evidence-провайдера → EvidenceKind, который он даёт. Пока провайдеры не
# несут собственного реестра (переедет в bundle 3.6), связываем здесь.
# Имя плагина-провайдера → вид evidence. Единственное определение: CLI как
# composition root импортирует его отсюда. Переезжает в реестр провайдеров
# бандла (3.6), когда тот появится.
PROVIDER_KINDS = {
    "log-regex": "tool_calls",
    "trace": "tool_calls",
    "db-query": "memory_snapshot",
    "http-canary": "external_callback",
}


@dataclass(frozen=True)
class Unsupported:
    template_id: str
    kind: str          # "not_applicable" | "unsupported"
    reason: str


def profile_capabilities(profile: TargetProfile) -> set[str]:
    kinds = {PROVIDER_KINDS[item["provider"]] for item in profile.evidence
             if item.get("provider") in PROVIDER_KINDS}
    if profile.memory:
        kinds.add("memory_snapshot")
    return kinds


def profile_features(profile: TargetProfile) -> set[str]:
    features = set()
    if "commit_memory" in profile.entrypoint:
        features.add("memory_commit")
    for mode in profile.modes.values():
        if isinstance(mode, dict) and mode.get("scope") == "per_deployment":
            features.add("mode_per_deployment")
        else:
            features.add("mode_per_request")
    return features


def compose(template: Template, profile: TargetProfile,
            capabilities: set[str] | None = None) -> ScenarioSpec | Unsupported:
    capabilities = profile_capabilities(profile) if capabilities is None else capabilities
    boundaries = {b.id for b in profile.isolation}
    if template.boundary is not None and template.boundary not in boundaries:
        return Unsupported(template.id, "not_applicable",
                           f"цель не заявляет границу '{template.boundary}'")
    missing_ev = sorted(set(template.requires_evidence) - capabilities)
    if missing_ev:
        return Unsupported(template.id, "unsupported",
                           "нет источников: " + ", ".join(missing_ev))
    missing_ft = sorted(set(template.requires_features) - profile_features(profile))
    if missing_ft:
        return Unsupported(template.id, "unsupported",
                           "цель не поддерживает: " + ", ".join(missing_ft))
    enhanced = "memory_snapshot" in capabilities
    roles = profile.identities.get("roles", {})
    refs = [str(template.standard[k]) for k in ("asi", "llm") if template.standard.get(k)]
    refs += [str(a) for a in template.standard.get("atlas", [])]
    steps = [_bind_step(step) for step in template.steps]
    goal = [
        _bind_assertion(item)
        for item in template.success
        if item.get("when") != "enhanced" or enhanced
    ]
    data = {
        "id": f"{template.id}-{profile.name}",
        "name": template.title,
        "attack_class": template.standard.get("asi") or template.id,
        "standard_refs": refs,
        "description": template.title,
        "actor": next((role for role in ("attacker", *roles) if role in roles), "attacker"),
        "boundary": template.boundary,
        "reset_policy": "per_scenario",
        "params": {},
        "payloads": ["<payload>"] if any(s.get("payload") for s in steps) else [],
        "steps": steps,
        "goal": goal,
        "remediation": template.remediation,
    }
    return ScenarioSpec.from_mapping(data)


def _bind_step(step: dict) -> dict:
    act = step["act"]
    bound = {"name": act, "actor": step["role"]}
    if act in ("inject", "deliver") or step.get("payload"):
        bound["payload"] = True
    elif act == "commit_memory":
        bound["name"] = "finalize"
        bound["commit_memory"] = True
    else:
        bound["message"] = step["message"]
    return bound


def _bind_assertion(item: dict) -> dict:
    goal = {("type" if key == "assert" else key): value
            for key, value in item.items() if key != "when"}
    # Enhanced evidence strengthens the explanation but must not veto the
    # primary state proof.  For example, a confirmed foreign tool call remains
    # a finding even when a memory snapshot cannot prove how it was induced.
    if item.get("when") == "enhanced":
        goal["optional"] = True
    return goal
