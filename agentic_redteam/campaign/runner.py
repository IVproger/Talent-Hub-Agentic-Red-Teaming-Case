"""Unified campaign runner.

Two-stage model: payloads are a fixed list produced once upstream (stage 1);
this runner (stage 2) executes them and never regenerates in the loop. Per
attempt: reset → mark → run the scenario's step chain → collect facts →
predicates → verdict. The chain is what makes a multi-step attack one attempt:
an injection and the later activation by a different role share one reset and
one evidence window. Transport failure or a failed evidence source yields
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
from ..assertions.verdict import CheckOutcome, verdict
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


@dataclass
class RunnerDeps:
    adapter: Any
    evidence: Any            # EvidenceSource: mark()/collect_facts(marker)/reset()
    id_factory: Any = None
    now: Any = None
    telemetry: Any = None       # optional run-observability; fail-open


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


def _evaluate_goal(goal: list[dict], facts: Facts, responses: dict[str, str], actor: str) -> list[CheckOutcome]:
    last = next(reversed(responses.values()), "") if responses else ""
    outcomes = []
    for assertion in goal:
        if assertion["type"] == "response_contains":
            # Bind to the step the assertion names; fall back to the chain's last reply.
            outcomes.append(P.response_contains(responses.get(assertion.get("at"), last),
                                                assertion["value"]))
        else:
            outcomes.append(evaluate(assertion, facts, actor))
    return outcomes


def _run_chain(steps, payload, mode, deps, index, run_id) -> dict[str, str]:
    """Run the chain in order; every actor keeps one session across its own steps."""
    responses: dict[str, str] = {}
    sessions: dict[str, Any] = {}
    for step in steps:
        if step.actor not in sessions:
            sessions[step.actor] = deps.adapter.open_session(
                step.actor, f"{run_id}-{index}-{step.actor}", mode or "vulnerable")
        session = sessions[step.actor]
        if step.commit_memory:
            session.commit_memory()
        else:
            responses[step.name] = session.send(payload if step.payload else step.message)
    return responses


def _run_attempt(index, payload, actor, mode, goal, deps, reset_policy, run_id, steps=()) -> AttemptResult:
    with _obs(deps.telemetry, "campaign.attempt"):
        try:
            if reset_policy != "none":
                deps.evidence.reset()
            marker = deps.evidence.mark()
            responses = _run_chain(steps or DEFAULT_CHAIN, payload, mode, deps, index, run_id)
            facts = deps.evidence.collect_facts(marker)
        except TargetUnavailable as exc:
            return AttemptResult(index, payload, actor, mode, "error", [], str(exc))
        except Exception as exc:  # evidence source failed → error, not a false success
            return AttemptResult(index, payload, actor, mode, "error", [], f"{type(exc).__name__}: {exc}")
        outcomes = _evaluate_goal(goal, facts, responses, actor)
        return AttemptResult(index, payload, actor, mode, verdict(outcomes), outcomes,
                             facts=deepcopy(facts),
                             observations=deepcopy(getattr(deps.evidence, "last_observations", {})))


def _asr(attempts: list[AttemptResult]) -> tuple[float, int | None]:
    scorable = [a for a in attempts if a.verdict in ("proven", "not_proven")]
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
) -> RunResult:
    modes = modes or [None]
    attempts: list[AttemptResult] = []
    index = 0
    for mode in modes:                 # per_deployment-friendly: group by mode
        for payload in payloads:       # fixed list; no regeneration here
            for _ in range(trials):
                index += 1
                attempts.append(_run_attempt(index, payload, actor, mode, goal, deps,
                                             reset_policy, run_id, steps))
    asr, first = _asr(attempts)
    return RunResult(run_id, "completed", attempts, asr, first)
