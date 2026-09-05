"""Deterministic, JSON-ready comparison of versioned target declarations."""
from copy import deepcopy
from dataclasses import asdict

from .schema import TargetProfile


def _compare(before: dict, after: dict) -> dict:
    return {
        "added": {key: deepcopy(after[key]) for key in sorted(after.keys() - before.keys())},
        "removed": {key: deepcopy(before[key]) for key in sorted(before.keys() - after.keys())},
        "changed": {key: {"before": deepcopy(before[key]), "after": deepcopy(after[key])}
                    for key in sorted(before.keys() & after.keys()) if before[key] != after[key]},
    }


def diff(a: TargetProfile, b: TargetProfile) -> dict:
    """Compare by stable names; version labels and list ordering are ignored.

    Each nonempty section has added/removed mappings and changed entries with
    before/after values. The returned data shares no mutable state with profiles.
    """
    a.validate()
    b.validate()
    sections = {
        "tools": ({x.name: asdict(x) for x in a.tools}, {x.name: asdict(x) for x in b.tools}),
        "roles": (a.identities.get("roles", {}), b.identities.get("roles", {})),
        "entrypoint": (a.entrypoint, b.entrypoint),
        "memory": ({x.id: asdict(x) for x in a.memory}, {x.id: asdict(x) for x in b.memory}),
    }
    result = {name: _compare(*values) for name, values in sections.items()}
    return {name: changes for name, changes in result.items() if any(changes.values())}
