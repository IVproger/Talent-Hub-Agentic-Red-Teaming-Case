"""Project a target's raw record into a normalized fact, per the profile.

The profile declares WHERE things are (dotted paths, principal_from); this
module reads them. Nothing here knows a target's field names.
"""
from __future__ import annotations

from typing import Any

from .facts import ObservedMemoryWrite, Persistence


def dotted(obj: Any, path: str) -> Any:
    """Resolve a dotted path; a `[]` suffix selects the list at that segment."""
    cur = obj
    for seg in path.split("."):
        if seg.endswith("[]"):
            seg = seg[:-2]
            cur = cur[seg] if seg else cur
        else:
            cur = cur[seg]
    return cur


def _scope(record: dict, decl: dict, store_scope: str | None) -> str:
    if store_scope is not None:
        return store_scope
    spec = decl.get("scope")
    if isinstance(spec, dict):
        raw = record.get(spec["field"])
        return spec.get("map", {}).get(raw, raw)
    return spec or ""


def project_memory(record: dict, decl: dict, store_scope: str | None) -> ObservedMemoryWrite:
    key = dotted(record, decl["key"]) if decl.get("key") else None
    owner = dotted(record, decl["owner"]) if decl.get("owner") else None
    return ObservedMemoryWrite(
        store_id=decl.get("store_id", ""),
        scope=_scope(record, decl, store_scope),
        key=str(key) if key is not None else None,
        content=str(dotted(record, decl["content"])),
        owner=str(owner) if owner is not None else None,
        persistence=Persistence.CONFIRMED,
        raw=record,
    )


def principal_of(args: dict, principal_from: dict, call_ctx: dict | None) -> str | None:
    kind = principal_from.get("kind")
    if kind == "argument":
        value = args.get(principal_from["name"])
    elif kind == "call_context":
        value = (call_ctx or {}).get(principal_from["field"])
    else:  # "none"
        value = None
    return str(value) if value is not None else None
