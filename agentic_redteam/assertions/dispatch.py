"""Dispatch a goal assertion (dict from a scenario) to its predicate."""
from __future__ import annotations

from ..normalize.facts import Facts, Persistence
from . import predicates as P
from .verdict import CheckOutcome, Grade


def evaluate(assertion: dict, facts: Facts, actor: str) -> CheckOutcome:
    t = assertion["type"]
    if t == "tool_principal_mismatch":
        return P.tool_principal_mismatch(facts, actor, assertion.get("at"), assertion.get("tool"))
    if t == "tool_principal_equals":
        return P.tool_principal_equals(facts, assertion["value"], assertion.get("at"), assertion.get("tool"))
    if t == "memory_write":
        persistence = Persistence(assertion["persistence"]) if assertion.get("persistence") else None
        return P.memory_write(facts, assertion["scope"], assertion.get("contains"), persistence)
    if t == "isolation_violation":
        return P.isolation_violation(facts, assertion["boundary"], actor, assertion.get("at"))
    if t == "cross_session_effect":
        return P.cross_session_effect(facts, actor, assertion.get("inject"), assertion.get("activate"))
    if t == "external_callback":
        return P.external_callback(facts, assertion["token"])
    if t == "response_contains":
        return CheckOutcome(False, Grade.TEXT, "response_contains требует ответ шага (в runner)")
    raise ValueError(f"unknown assertion type: {t}")
