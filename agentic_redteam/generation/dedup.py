"""Детерминированный дедуп payload'ов: Жаккар по токенам, без LLM."""
from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-zA-Zа-яА-Я0-9]+")


def tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN.finditer(text or "")}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def is_duplicate(candidate: str, prior: list[str], threshold: float = 0.85) -> bool:
    c = tokens(candidate)
    return any(jaccard(c, tokens(p)) >= threshold for p in prior)
