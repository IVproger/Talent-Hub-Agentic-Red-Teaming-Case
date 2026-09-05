"""Diff two memory snapshots: which records are new in `after`.

DB-agnostic — operates on normalized records. Identity is the record key when
the store provides one, otherwise a hash of the content.
"""
from __future__ import annotations

from hashlib import sha256

from .facts import ObservedMemoryWrite


def _identity(record: ObservedMemoryWrite) -> str:
    return record.key or sha256(record.content.encode()).hexdigest()


def diff(
    before: list[ObservedMemoryWrite], after: list[ObservedMemoryWrite]
) -> list[ObservedMemoryWrite]:
    seen = {_identity(r) for r in before}
    return [r for r in after if _identity(r) not in seen]
