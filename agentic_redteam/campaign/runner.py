"""Unified campaign runner.

Two-stage model: payloads are a fixed list produced once upstream (stage 1);
this runner (stage 2) executes them and never regenerates in the loop. Per
attempt: reset → mark → send → collect facts → predicates → verdict. Transport
failure or a failed evidence source yields verdict `error`, excluded from ASR.

Target-independent: operates on principals/facts, not a target's field names or
data stores. The evidence source is any object with
mark()/collect_facts(marker)->Facts/reset() — the real EvidenceBundle
(Task 3.6) implements it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..adapters.base import TargetUnavailable
from ..assertions import predicates as P
from ..assertions.dispatch import evaluate
from ..assertions.verdict import CheckOutcome, verdict
from ..normalize.facts import Facts


@dataclass
class RunnerDeps:
    adapter: Any
    evidence: Any            # EvidenceSource: mark()/collect_facts(marker)/reset()
    id_factory: Any = None
    now: Any = None


@dataclass
class AttemptResult:
    attempt: int
    payload: str
    actor: str
    mode: str | None
    verdict: str
    outcomes: list[CheckOutcome] = field(default_factory=list)
    error: str | None = None


@dataclass
class RunResult:
    run_id: str
    status: str
    attempts: list[AttemptResult]
    asr_percent: float
    attempts_to_first_proven: int | None = None


def _evaluate_goal(goal: list[dict], facts: Facts, response: str, actor: str) -> list[CheckOutcome]:
    outcomes = []
    for assertion in goal:
        if assertion["type"] == "response_contains":
            outcomes.append(P.response_contains(response, assertion["value"]))
        else:
            outcomes.append(evaluate(assertion, facts, actor))
    return outcomes


def _run_attempt(index, payload, actor, mode, goal, deps, reset_policy, run_id) -> AttemptResult:
    try:
        if reset_policy != "none":
            deps.evidence.reset()
        marker = deps.evidence.mark()
        session = deps.adapter.open_session("attacker", f"{run_id}-{index}", mode or "vulnerable")
        response = session.send(payload)
        facts = deps.evidence.collect_facts(marker)
    except TargetUnavailable as exc:
        return AttemptResult(index, payload, actor, mode, "error", [], str(exc))
    except Exception as exc:  # evidence source failed → error, not a false success
        return AttemptResult(index, payload, actor, mode, "error", [], f"{type(exc).__name__}: {exc}")
    outcomes = _evaluate_goal(goal, facts, response, actor)
    return AttemptResult(index, payload, actor, mode, verdict(outcomes), outcomes)


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
) -> RunResult:
    modes = modes or [None]
    attempts: list[AttemptResult] = []
    index = 0
    for mode in modes:                 # per_deployment-friendly: group by mode
        for payload in payloads:       # fixed list; no regeneration here
            for _ in range(trials):
                index += 1
                attempts.append(_run_attempt(index, payload, actor, mode, goal, deps, reset_policy, run_id))
    asr, first = _asr(attempts)
    return RunResult(run_id, "completed", attempts, asr, first)
