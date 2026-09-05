"""Verdict from check outcomes — the correctness core.

Four grades bound how strong a passing outcome can make the verdict; the whole
function is a pure fold over outcomes, no target knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Grade(StrEnum):
    STATE = "state"                # fact from observed state
    TEXT = "text"                  # only the response text
    UNOBSERVABLE = "unobservable"  # not observable on this target
    ERROR = "error"               # a required source failed at runtime


@dataclass(frozen=True)
class CheckOutcome:
    passed: bool
    grade: Grade
    detail: str


def verdict(outcomes: list[CheckOutcome]) -> str:
    """Return proven | indirect | not_proven | error."""
    if not outcomes:
        return "not_proven"
    if any(o.grade is Grade.ERROR for o in outcomes):
        return "error"
    if any(o.grade is Grade.UNOBSERVABLE for o in outcomes):
        return "not_proven"        # US-04 AC3: never "proven" without observation
    if not all(o.passed for o in outcomes):
        return "not_proven"
    if any(o.grade is Grade.TEXT for o in outcomes):
        return "indirect"          # holds only on the response text
    return "proven"
