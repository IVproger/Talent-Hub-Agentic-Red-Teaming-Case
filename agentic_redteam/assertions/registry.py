"""Predicate type → the EvidenceKind names it needs. Used by the capability gate."""
from __future__ import annotations

REQUIRED: dict[str, set[str]] = {
    "tool_principal_mismatch": {"tool_calls"},
    "tool_principal_equals": {"tool_calls"},
    "isolation_violation": {"tool_calls"},
    "cross_session_effect": {"tool_calls"},
    "memory_write": {"memory_snapshot"},
    "memory_commit_scope": set(),        # from the adapter's commit_memory response
    "external_callback": {"external_callback"},
    "response_contains": set(),          # text only
}


def required_kinds(goal: list[dict]) -> set[str]:
    kinds: set[str] = set()
    for assertion in goal:
        kinds |= REQUIRED.get(assertion["type"], set())
    return kinds
