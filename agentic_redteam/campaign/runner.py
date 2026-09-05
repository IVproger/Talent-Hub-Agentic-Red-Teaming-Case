"""Unified campaign runner.

Two-stage model: payloads are a fixed list produced once upstream (stage 1);
this runner (stage 2) executes them and never regenerates in the loop. Per
attempt: reset → mark → run the scenario's step chain → collect facts →
predicates → verdict. The chain is what makes a multi-step attack one attempt:
an injection and the later activation by a different role share one reset,
with a separate evidence window and actual principal for each step. Transport failure or a failed evidence source yields
verdict `error`, excluded from ASR.

Target-independent: operates on principals/facts, not a target's field names or
data stores. The evidence source is any object with
mark()/collect_facts(marker)->Facts/reset() — the real EvidenceBundle
(Task 3.6) implements it.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..adapters.base import TargetUnavailable
from ..assertions import predicates as P
from ..assertions.dispatch import evaluate
from ..assertions.verdict import CheckOutcome, Grade, verdict
from ..normalize.facts import Facts


@dataclass(frozen=True)
class ScenarioStep:
    """One turn of a scenario chain: who speaks and what they send."""

    name: str
    actor: str                  # role name, resolved to a principal by the adapter
    message: str | None = None  # literal text; None when the step carries the payload
    payload: bool = False       # this step's message comes from the payload variant
    commit_memory: bool = False # no message: commit the session's memory instead
    boundary: str | None = None


# A scenario with no chain is a single attacker turn carrying the payload.
DEFAULT_CHAIN = (ScenarioStep("attack", "attacker", payload=True),)


@dataclass(frozen=True)
class RunEvent:
    """Progress signal. Field names match the legacy pipeline's so listeners port over."""

    stage: str                  # "scenario" | "attempt" | "report" | "completed"
    message: str
    status: str = "running"
    attempt: int | None = None
    total: int | None = None
    data: dict = field(default_factory=dict)


def emit(on_event, event: RunEvent) -> None:
    """Progress is observation, not evidence: a broken listener must not end a run."""
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        pass


@dataclass
class RunnerDeps:
    adapter: Any
    evidence: Any            # EvidenceSource: mark()/collect_facts(marker)/reset()
    id_factory: Any = None
    now: Any = None
    telemetry: Any = None       # optional run-observability; fail-open


@dataclass
class StepEvidence:
    name: str
    role: str
    principal: str
    session_id: str
    facts: Facts | None = None
    observations: dict = field(default_factory=dict)
    response: str | None = None
    error: str | None = None


@dataclass
class AttemptResult:
    attempt: int
    payload: str
    actor: str
    mode: str | None
    verdict: str
    outcomes: list[CheckOutcome] = field(default_factory=list)
    error: str | None = None
    facts: Facts | None = None
    observations: dict = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    steps: list[StepEvidence] = field(default_factory=list)


@dataclass
class RunResult:
    run_id: str
    status: str
    attempts: list[AttemptResult]
    asr_percent: float
    attempts_to_first_proven: int | None = None


class _Guarded:
    """Wraps a telemetry context manager so telemetry never breaks the run."""

    def __init__(self, cm):
        self._cm = cm

    def __enter__(self):
        try:
            return self._cm.__enter__()
        except Exception:
            return None

    def __exit__(self, *args):
        try:
            self._cm.__exit__(*args)
        except Exception:
            pass
        return False


def _obs(telemetry, name):
    if telemetry is None:
        return nullcontext()
    try:
        return _Guarded(telemetry.observation(name))
    except Exception:
        return nullcontext()


def _aggregate(steps):
    facts, observations = Facts(), {}
    for step in steps:
        if step.facts is None:
            continue
        for name in ("tool_calls", "memory_writes", "callbacks"):
            getattr(facts, name).extend(getattr(step.facts, name))
        for source, records in step.observations.items():
            observations.setdefault(source, []).extend(records)
    return facts, observations


def _selected_step(assertion):
    return assertion.get("at") or (
        assertion.get("activate") if assertion["type"] == "cross_session_effect" else None)


def validate_step_references(goal, steps):
    names = [step.name for step in steps]
    if len(set(names)) != len(names):
        raise ValueError("Имена шагов должны быть уникальны.")
    for assertion in goal:
        fields = ("at", "inject", "activate") if assertion["type"] == "cross_session_effect" else ("at",)
        for field_name in fields:
            if assertion.get(field_name) is not None and assertion[field_name] not in names:
                raise ValueError(f"Неизвестный шаг в {field_name}: {assertion[field_name]}")
        if assertion["type"] == "cross_session_effect":
            if assertion.get("at") and assertion.get("activate") and assertion["at"] != assertion["activate"]:
                raise ValueError("at и activate должны указывать на один шаг.")
            if assertion.get("inject") and assertion.get("activate"):
                if names.index(assertion["inject"]) >= names.index(assertion["activate"]):
                    raise ValueError("inject должен предшествовать activate.")


def _evaluate_goal(goal, facts, steps, actor, implicit=False):
    by_name = {step.name: step for step in steps}
    outcomes = []
    identity_checks = {"tool_principal_mismatch", "isolation_violation", "cross_session_effect"}
    for assertion in goal:
        selector = _selected_step(assertion)
        selected = by_name.get(selector) if selector else None
        # Older direct run_scenario callers used arbitrary 'at' labels for the
        # implicit single turn. Explicit chains always validate references.
        if selector and selected is None and implicit:
            selected = steps[0]
        if assertion["type"] == "response_contains":
            reply = (selected.response if selected else
                     next((step.response for step in reversed(steps) if step.response is not None), ""))
            outcome = P.response_contains(reply or "", assertion["value"])
        elif selected:
            outcome = evaluate(assertion, selected.facts, selected.principal)
        elif assertion["type"] in identity_checks:
            per_step = [evaluate(assertion, step.facts, step.principal) for step in steps]
            outcome = (next((o for o in per_step if o.passed), None)
                       or next((o for o in per_step if o.grade == Grade.UNOBSERVABLE), None)
                       or per_step[0])
        else:
            # Unscoped memory predicates see the writes from the whole chain,
            # including finalization, even when activation wrote nothing.
            outcome = evaluate(assertion, facts, actor)
        if selected:
            outcome = CheckOutcome(outcome.passed, outcome.grade,
                f"{selected.name} ({selected.role}, principal={selected.principal}): {outcome.detail}")
        outcomes.append(outcome)
    return outcomes


def _run_chain(steps, payload, mode, deps, index, run_id, evidence, reset_policy):
    """Every role keeps its session; each step owns its mark/collect window."""
    sessions: dict[str, Any] = {}
    for step in steps:
        if reset_policy == "per_step":
            deps.evidence.reset()
        if step.actor not in sessions:
            sessions[step.actor] = deps.adapter.open_session(
                step.actor, f"{run_id}-{index}-{step.actor}", mode or "vulnerable")
        session = sessions[step.actor]
        current = StepEvidence(step.name, step.actor, session.principal.value, session.session_id)
        evidence.append(current)
        try:
            marker = deps.evidence.mark()
            if step.commit_memory:
                session.commit_memory()
            else:
                current.response = session.send(payload if step.payload else step.message)
            current.facts = deepcopy(deps.evidence.collect_facts(marker))
            current.observations = deepcopy(getattr(deps.evidence, "last_observations", {}))
        except Exception as exc:
            current.error = f"{type(exc).__name__}: {exc}"
            raise


def _run_attempt(index, payload, actor, mode, goal, deps, reset_policy, run_id, steps=()) -> AttemptResult:
    with _obs(deps.telemetry, "campaign.attempt"):
        evidence = []
        try:
            if steps:
                validate_step_references(goal, steps)
            if reset_policy == "per_scenario":
                deps.evidence.reset()
            _run_chain(steps or DEFAULT_CHAIN, payload, mode, deps, index, run_id, evidence, reset_policy)
            facts, observations = _aggregate(evidence)
            outcomes = _evaluate_goal(goal, facts, evidence, actor, implicit=not steps)
        except KeyboardInterrupt as exc:
            facts, observations = _aggregate(evidence)
            exc.attempt = AttemptResult(index, payload, actor, mode, "error", [], "Прервано пользователем",
                facts=facts if any(s.facts is not None for s in evidence) else None,
                observations=observations, steps=evidence)
            raise
        except Exception as exc:  # incomplete execution/evidence is always error
            facts, observations = _aggregate(evidence)
            error = str(exc) if isinstance(exc, TargetUnavailable) else f"{type(exc).__name__}: {exc}"
            return AttemptResult(index, payload, actor, mode, "error", [], error,
                                 facts=facts if any(s.facts is not None for s in evidence) else None,
                                 observations=observations, steps=evidence)
        return AttemptResult(index, payload, actor, mode, verdict([o for a, o in zip(goal, outcomes) if not a.get("optional", False)]), outcomes,
                             facts=facts, observations=observations, steps=evidence)


def _asr(attempts: list[AttemptResult]) -> tuple[float, int | None]:
    scorable = [a for a in attempts if a.verdict != "error"]
    asr = (sum(a.verdict == "proven" for a in scorable) / len(scorable) * 100) if scorable else 0.0
    first = next((a.attempt for a in attempts if a.verdict == "proven"), None)
    return asr, first


def run_scenario(
    payloads: list[str],
    goal: list[dict],
    actor: str,
    deps: RunnerDeps,
    modes: list[str | None] | None = None,
    trials: int = 1,
    reset_policy: str = "per_scenario",
    run_id: str = "run",
    steps: list[ScenarioStep] | None = None,
    on_event=None,
    on_attempt=None,
    should_stop=None,
) -> RunResult:
    modes = modes or [None]
    attempts: list[AttemptResult] = []
    total = len(modes) * len(payloads) * trials
    index = 0
    for mode in modes:                 # per_deployment-friendly: group by mode
        for payload in payloads:       # fixed list; no regeneration here
            for _ in range(trials):
                if should_stop and should_stop():
                    raise KeyboardInterrupt()
                index += 1
                try:
                    attempt = _run_attempt(index, payload, actor, mode, goal, deps,
                                           reset_policy, run_id, steps)
                except KeyboardInterrupt as exc:
                    if getattr(exc, "attempt", None) is not None and on_attempt:
                        on_attempt(exc.attempt)
                    raise
                attempts.append(attempt)
                if on_attempt:
                    on_attempt(attempt)
                emit(on_event, RunEvent(
                    "attempt", f"попытка {index}/{total}: {attempt.verdict}",
                    attempt=index, total=total,
                    data={"verdict": attempt.verdict, "mode": mode, "error": attempt.error}))
    asr, first = _asr(attempts)
    return RunResult(run_id, "completed", attempts, asr, first)
