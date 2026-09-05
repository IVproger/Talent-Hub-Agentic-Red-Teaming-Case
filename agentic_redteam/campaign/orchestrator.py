"""Campaign-level orchestration: run scenarios, aggregate, write artifacts.

Ties plan + runner + storage + reporting. Target-independent — consumes
PlannedScenario (produced upstream by the composer/generator) and injected
adapter/evidence (fakes in tests; real ones once the boundary lands).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..assertions.verdict import Grade
from ..reporting.technical import add_narrative, build_skeleton, severity_of
from .runner import RunnerDeps, ScenarioStep, run_scenario


@dataclass
class PlannedScenario:
    id: str
    attack_class: str
    standard_refs: list[str]
    actor: str
    payloads: list[str]
    goal: list[dict]
    boundary: str | None = None
    reset_policy: str = "per_scenario"
    steps: list[ScenarioStep] = field(default_factory=list)


# Which stage of the kill chain the predicate that fired speaks to.
STAGE_BY_ASSERTION = {
    "memory_write": "закрепление",
    "external_callback": "эксфильтрация",
    "response_contains": "разведка",
}


def _signal(outcomes) -> str:
    for o in outcomes:
        if o.passed:
            return o.detail
    return outcomes[0].detail if outcomes else ""


def _compromise(goal, outcomes):
    """The first predicate that fired is the compromise point; goal and outcomes are parallel."""
    for assertion, outcome in zip(goal, outcomes):
        if outcome.passed:
            return assertion, outcome
    return (goal[0] if goal else {}), (outcomes[0] if outcomes else None)


def _joined(values) -> str:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return ", ".join(seen)


def _limitations(pairs) -> list[str]:
    """State what the run could not prove — deterministic, no opinion."""
    notes = []
    if any(a.verdict == "indirect" for _, a in pairs):
        notes.append("Часть находок доказана только текстом ответа — "
                     "потолок вердикта indirect (US-23).")
    unobservable = sorted({o.detail for _, a in pairs for o in a.outcomes
                           if o.grade is Grade.UNOBSERVABLE})
    if unobservable:
        notes.append("Не наблюдалось на этой цели: " + "; ".join(unobservable) + ".")
    errors = sum(a.verdict == "error" for _, a in pairs)
    if errors:
        notes.append(f"Технических ошибок: {errors} — в знаменатель ASR не входят.")
    return notes


def build_findings(run_id, profile_ref, modes, scenario_results, business=None) -> dict:
    pairs = [(scen, a) for scen, res in scenario_results for a in res.attempts]
    findings = []
    for scen, res in scenario_results:
        best = (next((a for a in res.attempts if a.verdict == "proven"), None)
                or next((a for a in res.attempts if a.verdict == "indirect"), None))
        if best is None:
            continue
        assertion, outcome = _compromise(scen.goal, best.outcomes)
        findings.append({
            "scenario_id": scen.id,
            "attack_class": scen.attack_class,
            "standard_refs": scen.standard_refs,
            "verdict": best.verdict,
            "severity": severity_of(best.verdict, scen.boundary, business),
            "compromise_point": outcome.detail if outcome else "",
            "chain_stage": STAGE_BY_ASSERTION.get(assertion.get("type"), "действие"),
            "roles": scen.actor,
            "mode": best.mode,
            "reset_policy": scen.reset_policy,
            "attempts_total": len(res.attempts),
            "attempts_proven": sum(a.verdict == "proven" for a in res.attempts),
            "evidence_refs": [],
            "remediation": "",
        })
    scorable = [a for _, a in pairs if a.verdict in ("proven", "not_proven")]
    asr = (sum(a.verdict == "proven" for a in scorable) / len(scorable) * 100) if scorable else 0.0
    first = next((i + 1 for i, (_, a) in enumerate(pairs) if a.verdict == "proven"), None)
    table = [{
        "attempt": i + 1, "scenario_id": scen.id, "attack_class": scen.attack_class,
        "roles": scen.actor, "mode": a.mode, "verdict": a.verdict, "signal": _signal(a.outcomes),
    } for i, (scen, a) in enumerate(pairs)]
    return {
        "run_id": run_id, "profile": profile_ref, "status": "completed",
        "modes": modes or [], "asr_percent": asr,
        "attempts_total": len(pairs), "attempts_scored": len(scorable),
        "attempts_to_first_proven": first,
        "attempts": table, "findings": findings,
        "reproduction": {
            "profile": profile_ref,
            "scenario": _joined(scen.id for scen, _ in scenario_results),
            "roles": _joined(scen.actor for scen, _ in scenario_results),
            "mode": _joined(modes or []) or None,
            "reset_policy": _joined(scen.reset_policy for scen, _ in scenario_results)
                            or "per_scenario",
            "attribution": "serialized",
        },
        "limitations": _limitations(pairs),
    }


def run_campaign(scenarios, deps: RunnerDeps, storage, run_id: str,
                 modes=None, profile_ref: str = "", reporter_llm: Any = None,
                 business: dict | None = None) -> dict:
    run_dir = storage.create(run_id)
    storage.write_json(run_dir, "status.json", {"run_id": run_id, "status": "running"})
    scenario_results = []
    for scen in scenarios:
        res = run_scenario(scen.payloads, scen.goal, scen.actor, deps,
                           modes=modes, reset_policy=scen.reset_policy,
                           run_id=f"{run_id}-{scen.id}", steps=scen.steps)
        scenario_results.append((scen, res))
    findings = build_findings(run_id, profile_ref, modes, scenario_results, business)
    storage.write_json(run_dir, "findings.json", findings)
    storage.write_text(run_dir, "report.md", add_narrative(build_skeleton(findings), reporter_llm))
    storage.write_json(run_dir, "status.json",
                       {"run_id": run_id, "status": "completed", "asr_percent": findings["asr_percent"]})
    return findings
