"""Normalized, target-independent facts.

These are what evidence providers produce after normalization; predicates and
the verdict operate only on these — never on the target's raw output or the
chat text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Persistence(StrEnum):
    CONFIRMED = "confirmed"   # memory write seen in a state snapshot diff
    ATTEMPTED = "attempted"   # inferred from an observed memory-tool call


@dataclass(frozen=True)
class ObservedToolCall:
    tool: str
    principal: str | None
    args: dict[str, str]
    raw: str


@dataclass(frozen=True)
class ObservedMemoryWrite:
    store_id: str
    scope: str
    key: str | None
    content: str
    owner: str | None
    persistence: Persistence
    raw: dict


@dataclass(frozen=True)
class ObservedCallback:
    token: str
    source: str


@dataclass
class Facts:
    """Container that collect→normalize fills; consumed by predicates."""
    tool_calls: list[ObservedToolCall] = field(default_factory=list)
    memory_writes: list[ObservedMemoryWrite] = field(default_factory=list)
    callbacks: list[ObservedCallback] = field(default_factory=list)
