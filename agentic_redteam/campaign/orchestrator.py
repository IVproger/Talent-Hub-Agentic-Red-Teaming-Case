"""Campaign-level orchestration: run scenarios, aggregate, write artifacts.

Ties plan + runner + storage + reporting. Target-independent — consumes
PlannedScenario (produced upstream by the composer/generator) and injected
adapter/evidence (fakes in tests; real ones once the boundary lands).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


def _signal(outcomes) -> str:
    for o in outcomes:
        if o.passed:
            return o.detail
    return outcomes[0].detail if outcomes else ""


def build_findings(run_id, profile_ref, modes, scenario_results, business=None) -> dict:
    pairs = [(scen, a) for scen, res in scenario_results for a in res.attempts]
    findings = []
    for scen, res in scenario_results:
        best = (next((a for a in res.attempts if a.verdict == "proven"), None)
                or next((a for a in res.attempts if a.verdict == "indirect"), None))
        if best is not None:
            findings.append({
                "scenario_id": scen.id,
                "attack_class": scen.attack_class,
                "standard_refs": scen.standard_refs,
                "verdict": best.verdict,
                "severity": severity_of(best.verdict, scen.boundary, business),
                "compromise_point": _signal(best.outcomes),
                "chain_stage": "действие",
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
    head = scenario_results[0][0] if scenario_results else None
    return {
        "run_id": run_id, "profile": profile_ref, "status": "completed",
        "modes": modes or [], "asr_percent": asr,
        "attempts_total": len(pairs), "attempts_scored": len(scorable),
        "attempts_to_first_proven": first,
        "attempts": table, "findings": findings,
        "reproduction": {
            "profile": profile_ref,
            "scenario": head.id if head else "",
            "roles": head.actor if head else "",
            "mode": (modes or [None])[0],
            "reset_policy": head.reset_policy if head else "per_scenario",
            "attribution": "serialized",
        },
        "limitations": [],
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
                           run_id=f"{run_id}-{scen.id}")
        scenario_results.append((scen, res))
    findings = build_findings(run_id, profile_ref, modes, scenario_results, business)
    storage.write_json(run_dir, "findings.json", findings)
    storage.write_text(run_dir, "report.md", add_narrative(build_skeleton(findings), reporter_llm))
    storage.write_json(run_dir, "status.json",
                       {"run_id": run_id, "status": "completed", "asr_percent": findings["asr_percent"]})
    return findings
