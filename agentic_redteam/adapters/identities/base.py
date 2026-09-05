from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..base import Principal


@dataclass(frozen=True)
class Credential:
    principal: Principal
    headers: dict[str, str] = field(repr=False)
    body_fields: dict[str, str] = field(repr=False)


@runtime_checkable
class IdentityProvider(Protocol):
    def acquire(self, role: str) -> Credential: ...
    def release(self, credential: Credential) -> None: ...
