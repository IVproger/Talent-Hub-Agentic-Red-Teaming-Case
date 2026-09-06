"""Stable machine statuses and human-facing autonomous-attempt labels."""
from __future__ import annotations

from typing import Any


UNSCORED_LABEL = "НЕ ОЦЕНЕНО"

_REASON_LABELS = {
    "attacker_turn_timeout": "таймаут решения атакующего",
    "attacker_invalid_action": "невалидное действие атакующего",
    "judge_failure": "сбой judge",
    "attempt_failure": "технический сбой попытки",
}


def classify_unscored(
    stop_reason: str | None,
    attempt_error: str | None,
    outcome_error: str | None = None,
) -> str | None:
    """Classify an unscored result without changing its stable status."""
    if not attempt_error and not outcome_error:
        return None
    if stop_reason == "turn_timeout":
        return "attacker_turn_timeout"
    if stop_reason == "llm_failure":
        return "attacker_invalid_action"
    if attempt_error:
        return "attempt_failure"
    return "judge_failure"


def attempt_outcome_label(row: dict[str, Any]) -> str:
    """Return a concise human label while preserving JSON ``status=error``."""
    verdict = row.get("judge_verdict")
    if verdict in {"YES", "NO"}:
        return str(verdict)
    if row.get("status") == "excluded":
        return "ИСКЛЮЧЕНО"
    if row.get("status") != "error":
        return str(row.get("status") or "—")
    reason = row.get("unscored_reason") or classify_unscored(
        row.get("stop_reason"), row.get("error"), None
    )
    detail = _REASON_LABELS.get(str(reason), "технический сбой")
    return f"{UNSCORED_LABEL} · {detail}"
