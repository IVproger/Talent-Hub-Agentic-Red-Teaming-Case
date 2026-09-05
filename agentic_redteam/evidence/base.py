"""Raw evidence contracts shared by providers, calibration, and normalization."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class EvidenceKind(StrEnum):
    MEMORY_SNAPSHOT = "memory_snapshot"
    TOOL_CALLS = "tool_calls"
    EXTERNAL_CALLBACK = "external_callback"
    AUDIT_LOG = "audit_log"
    SESSION_RESET = "session_reset"


@dataclass(frozen=True)
class Marker:
    """An opaque cursor interpreted only by the provider that issued it."""

    token: str


@dataclass(frozen=True)
class Observation:
    """Raw source data; conversion to normalized facts belongs to the core."""

    kind: EvidenceKind
    payload: dict
    raw: str


@dataclass(frozen=True)
class CalibrationResult:
    """Read-only binding check: success flag and a user-facing explanation.

    The spec names this result without prescribing fields. ``ok``/``message``
    match the existing CheckResult vocabulary; the bundle adds the provider id
    when presenting per-provider results. A failed check must never count as
    successful evidence collection.
    """

    ok: bool
    message: str = ""


@runtime_checkable
class EvidenceProvider(Protocol):
    kind: EvidenceKind

    def calibrate(self) -> CalibrationResult:
        """Check reachability and declared bindings without mutating the target."""
        ...

    def mark(self) -> Marker:
        """Capture a source boundary before an action is executed."""
        ...

    def collect(self, since: Marker) -> list[Observation]:
        """Read observations since the marker (or the current memory snapshot).

        Source failures must propagate, not become an empty successful result:
        required evidence is load-bearing even when run telemetry is fail-open.
        """
        ...
