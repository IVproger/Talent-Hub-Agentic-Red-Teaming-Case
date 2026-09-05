"""Transport boundary contracts; no target I/O is performed by this module."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..doctor import CheckResult


@dataclass(frozen=True)
class Principal:
    attribute: str
    value: str


class AdapterFeature(StrEnum):
    SESSIONS = "sessions"
    MEMORY_COMMIT = "memory_commit"
    MODE_PER_REQUEST = "mode_per_request"
    MODE_PER_DEPLOYMENT = "mode_per_deployment"


class UnsupportedFeature(RuntimeError):
    """The target does not offer an explicitly requested capability."""


class TargetUnavailable(RuntimeError):
    """Transport failure; the attempt is an error, not a negative verdict."""


@runtime_checkable
class TargetSession(Protocol):
    principal: Principal
    session_id: str

    def send(self, message: str) -> str:
        """Send a user message; transport failures raise TargetUnavailable."""
        ...

    def commit_memory(self) -> list[dict]:
        """Return raw records; raise UnsupportedFeature without MEMORY_COMMIT."""
        ...


@runtime_checkable
class TargetAdapter(Protocol):
    features: frozenset[AdapterFeature]

    def preflight(self) -> list[CheckResult]:
        """Check target availability without changing its state."""
        ...

    def open_session(self, role: str, session_id: str, mode: str) -> TargetSession:
        """Acquire the role's principal and open a session in the campaign mode."""
        ...

    def close(self) -> None:
        """Release resources owned by this adapter."""
        ...
