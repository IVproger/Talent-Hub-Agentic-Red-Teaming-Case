"""Campaign-level orchestration: run scenarios, aggregate, write artifacts.

Ties plan + runner + storage + reporting. Target-independent — consumes
PlannedScenario (produced upstream by the composer/generator) and injected
adapter/evidence (fakes in tests; real ones once the boundary lands).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..assertions.verdict import Grade
from ..reporting.technical import add_narrative, build_skeleton, severity_of, remediation_for
from .runner import RunnerDeps, ScenarioStep, RunResult, RunEvent, emit, run_scenario


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
    expect: str = "attack_success"
    remediation: str = ""


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
        if outcome.passed and not assertion.get("optional", False):
            return assertion, outcome
    return (goal[0] if goal else {}), (outcomes[0] if outcomes else None)


def _joined(values) -> str:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return ", ".join(seen)


def _attempt_roles(attempt) -> str:
    return _joined(f"{step.role} ({step.principal})" for step in attempt.steps) or attempt.actor


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


def _diversity(scenario_results, pairs) -> dict:
    """US-13: чем кампания прошлась, а не сколько раз пробила.

    Показывается наравне с ASR: успешность легко накрутить повтором одной
    удачной попытки, покрытие и разнообразие — нет. Ошибочная попытка ничего
    не доказала, поэтому в затронутую поверхность не входит.
    """
    scored = [a for _, a in pairs if a.verdict != "error"]
    tools, stores = set(), set()
    for attempt in scored:
        if attempt.facts is None:
            continue
        tools.update(call.tool for call in attempt.facts.tool_calls)
        stores.update(write.store_id for write in attempt.facts.memory_writes)
    return {
        "scenarios": len(scenario_results),
        "attack_classes": sorted({scen.attack_class for scen, _ in scenario_results
                                  if scen.attack_class}),
        "standard_refs": sorted({ref for scen, _ in scenario_results
                                 for ref in scen.standard_refs}),
        "payloads": len({a.payload for a in scored if a.payload}),
        "boundaries": sorted({scen.boundary for scen, _ in scenario_results if scen.boundary}),
        "tools": sorted(tools),
        "stores": sorted(stores),
    }


def build_findings(run_id, profile_ref, modes, scenario_results, business=None) -> dict:
    pairs = [(scen, a) for scen, res in scenario_results for a in res.attempts]
    findings = []
    for scen, res in scenario_results:
        best = (next((a for a in res.attempts if a.verdict == "proven"), None)
                or next((a for a in res.attempts if a.verdict == "indirect"), None))
        if best is None or scen.expect == "pass":
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
            "roles": _attempt_roles(best),
            "mode": best.mode,
            "reset_policy": scen.reset_policy,
            "attempts_total": len(res.attempts),
            "attempts_proven": sum(a.verdict == "proven" for a in res.attempts),
            "evidence_refs": list(best.evidence_refs),
            "remediation": scen.remediation or remediation_for(scen.goal),
        })
    scorable = [a for scen, a in pairs if scen.expect != "pass" and a.verdict != "error"]
    groups = {}
    for scen, attempt in pairs:
        if scen.expect != "pass" and attempt.verdict != "error":
            groups.setdefault((scen.id, attempt.mode), []).append(attempt.verdict)
    per_mode = {}
    for (_, mode), values in groups.items():
        row = per_mode.setdefault(mode or "default", {"scenarios_scored": 0, "scenarios_proven": 0})
        row["scenarios_scored"] += 1
        row["scenarios_proven"] += "proven" in values
    for row in per_mode.values():
        row["asr_percent"] = 100 * row["scenarios_proven"] / row["scenarios_scored"]
    proven_groups = sum("proven" in values for values in groups.values())
    asr = 100 * proven_groups / len(groups) if groups else 0.0
    attempt_asr = 100 * sum(a.verdict == "proven" for a in scorable) / len(scorable) if scorable else 0.0
    first = next((i + 1 for i, (_, a) in enumerate(pairs) if a.verdict == "proven"), None)
    table = [{
        "attempt": i + 1, "scenario_id": scen.id, "attack_class": scen.attack_class,
        "roles": _attempt_roles(a), "mode": a.mode, "verdict": a.verdict, "signal": _signal(a.outcomes),
    } for i, (scen, a) in enumerate(pairs)]
    return {
        "run_id": run_id, "profile": profile_ref, "status": "completed",
        "modes": modes or [], "asr_percent": asr,
        "asr_by_mode": per_mode, "scenarios_scored": len(groups),
        "scenarios_proven": proven_groups, "attempt_asr_percent": attempt_asr,
        "smoke": [{"scenario_id": scen.id, "mode": a.mode,
                   "ok": a.verdict == "proven", "verdict": a.verdict}
                  for scen, a in pairs if scen.expect == "pass"],
        "attempts_total": len(pairs), "attempts_scored": len(scorable),
        "attempts_to_first_proven": first,
        "diversity": _diversity(scenario_results, pairs),
        "attempts": table, "findings": findings,
        "reproduction": {
            "profile": profile_ref,
            "scenario": _joined(scen.id for scen, _ in scenario_results),
            "roles": _joined(_attempt_roles(a) if a.steps else scen.actor for scen, a in pairs),
            "mode": _joined(modes or []) or None,
            "reset_policy": _joined(scen.reset_policy for scen, _ in scenario_results)
                            or "per_scenario",
            "attribution": "serialized",
        },
        "limitations": _limitations(pairs),
    }


def _campaign_record(run_id, profile_ref, modes, trials, scenarios) -> dict:
    """What was planned — written before execution so it survives a crash."""
    return {
        "run_id": run_id,
        "profile": profile_ref,
        "modes": list(modes or []),
        "trials": trials,
        "scenarios": list(scenarios),
    }


def _transcript_row(scen, attempt) -> dict:
    return {
        "scenario_id": scen.id,
        "attempt": attempt.attempt,
        "mode": attempt.mode,
        "actor": attempt.actor,
        "payload": attempt.payload,
        "verdict": attempt.verdict,
        "outcomes": [{"passed": o.passed, "grade": o.grade, "detail": o.detail}
                     for o in attempt.outcomes],
        "error": attempt.error,
        "evidence_refs": list(attempt.evidence_refs),
        "steps": [{"name": step.name, "role": step.role, "principal": step.principal,
                   "session_id": step.session_id, "evidence_complete": step.facts is not None,
                   "error": step.error} for step in attempt.steps],
    }


def run_campaign(scenarios, deps: RunnerDeps, storage, run_id: str,
                 modes=None, profile_ref: str = "", reporter_llm: Any = None,
                 business: dict | None = None, trials: int = 1,
                 on_event=None, should_stop=None, metadata=None, config=None,
                 mode_scope="per_request") -> dict:
    """Persist every attempt before starting the next; finalize even on Ctrl+C."""
    scenarios = list(scenarios)
    run_dir = storage.create(run_id)
    record = _campaign_record(run_id, profile_ref, modes, trials, scenarios)
    record.update(metadata or {})
    storage.write_campaign(run_dir, record)
    storage.write_json(run_dir, "config.json", config or {})
    storage.write_json(run_dir, "status.json", {"run_id": run_id, "status": "running"})
    results = {s.id: (s, RunResult(run_id, "running", [], 0.0)) for s in scenarios}
    evidence_index = 0
    status, error = "completed", None

    total = sum(max(1, len(s.payloads)) * len(modes or [None]) * trials for s in scenarios)
    def publish(stage, message, **data):
        emit(on_event, RunEvent(stage, message, status=stage,
             attempt=evidence_index, total=total, data=data))

    def persist(scen, attempt):
        nonlocal evidence_index
        evidence_index += 1
        if attempt.facts is not None:
            name = f"evidence-{evidence_index:04d}.json"
            storage.write_json(run_dir, name, {
                "scenario_id": scen.id, "attempt": attempt.attempt,
                "actor": attempt.actor, "mode": attempt.mode,
                "facts": attempt.facts, "observations": attempt.observations,
                "steps": attempt.steps,
            })
            attempt.evidence_refs = [name]
        storage.append_transcript(run_dir, _transcript_row(scen, attempt))
        results[scen.id][1].attempts.append(attempt)
        # Checkpoint human and machine artifacts too, so even process termination
        # leaves a usable last-completed-attempt result.
        checkpoint("running")
        publish("attempt", f"попытка {evidence_index}/{total}: {attempt.verdict}",
                scenario_id=scen.id, mode=attempt.mode, verdict=attempt.verdict, run_dir=str(run_dir))

    def checkpoint(current_status):
        findings = build_findings(run_id, profile_ref, modes, list(results.values()), business)
        findings.update(status=current_status, error=error)
        findings["coverage"] = record.get("coverage", {})
        findings["limitations"].extend(record.get("limitations", []))
        storage.write_json(run_dir, "findings.json", findings)
        storage.write_text(run_dir, "report.md", build_skeleton(findings))
        storage.write_json(run_dir, "status.json", {
            "run_id": run_id, "status": current_status, "asr_percent": findings["asr_percent"],
            "attempts_total": findings["attempts_total"], "error": error,
        })
        return findings

    try:
        checkpoint("running")
        batches = ([(s, [m]) for m in modes for s in scenarios]
                   if mode_scope == "per_deployment" and modes else [(s, modes) for s in scenarios])
        for scen, selected_modes in batches:
            publish("scenario", f"сценарий {scen.id}", scenario_id=scen.id)
            run_scenario(scen.payloads or [""], scen.goal, scen.actor, deps,
                         modes=selected_modes, trials=trials, reset_policy=scen.reset_policy,
                         run_id=f"{run_id}-{scen.id}-{'-'.join(selected_modes or [])}", steps=scen.steps,
                         on_attempt=lambda a, s=scen: persist(s, a), should_stop=should_stop)
    except KeyboardInterrupt:
        status, error = "interrupted", "Прервано пользователем"
    except Exception as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    publish("report", "Собираем отчёт")
    findings = checkpoint(status)
    if status == "completed":
        storage.write_text(run_dir, "report.md", add_narrative(build_skeleton(findings), reporter_llm))
    _write_observability(storage, run_dir, deps.telemetry)
    publish(status, f"{status}: ASR {findings['asr_percent']:.0f}%", run_id=run_id, run_dir=str(run_dir))
    if status == "interrupted":
        raise KeyboardInterrupt
    return findings


def _write_observability(storage, run_dir, telemetry) -> None:
    """Манифест связывает прогон с его трассой.

    Наблюдаемость нашего прогона fail-open: её отказ не меняет ни вердикт, ни
    остальные артефакты — они уже на диске к этому моменту.
    """
    if telemetry is None:
        return
    try:
        telemetry.flush()
        storage.write_json(run_dir, "observability.json", {
            "trace_id": telemetry.trace_id,
            "trace_url": telemetry.trace_url,
            "root_observation_id": telemetry.root_observation_id,
            "warning": telemetry.warning,
        })
    except Exception:
        pass


def _relay(on_event, scenario_id: str, offset: int, total: int):
    """Пересчитать номер попытки сценария в сквозной номер кампании."""
    if on_event is None:
        return None

    def relay(event: RunEvent) -> None:
        emit(on_event, RunEvent(event.stage, event.message, event.status,
                                offset + (event.attempt or 0), total,
                                {**event.data, "scenario_id": scenario_id}))
    return relay
