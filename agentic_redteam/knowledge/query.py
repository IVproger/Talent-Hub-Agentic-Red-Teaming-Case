"""Выборки базы знаний для генератора. Форма — как у generation.context."""
from __future__ import annotations


def _distinct(values):
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def context_for(store, profile_name: str) -> dict:
    rows = store.all_for(profile_name)
    return {
        "confirmed": _distinct(r["attack_class"] for r in rows if r["verdict"] == "proven"),
        "ineffective": _distinct(r["signal"] for r in rows if r["verdict"] == "not_proven"),
        "prior_payloads": _distinct(r["payload"] for r in rows),
    }
