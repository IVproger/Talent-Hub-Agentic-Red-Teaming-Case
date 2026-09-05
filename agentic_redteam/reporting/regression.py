"""E8: сравнение двух прогонов — закрылась ли находка и цел ли продукт.

Одна операция обслуживает обе оси: «до/после исправления» (US-29) и A/B по
режимам Ядра §6 — отличается только тем, какие два набора findings подать.
Работает на артефакте `findings.json`, поэтому не зависит ни от цели, ни от
того, чем прогон был выполнен.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CLOSED, REMAINED, APPEARED = "closed", "remained", "appeared"

RUSSIAN = {CLOSED: "перестала проходить", REMAINED: "осталась", APPEARED: "появилась"}


@dataclass
class RegressionDiff:
    per_attack: dict[str, str] = field(default_factory=dict)
    asr_before: float = 0.0
    asr_after: float = 0.0
    # None — штатных сценариев не было: «не проверяли», а не «всё цело».
    smoke_ok: bool | None = None
    smoke_checked: int = 0


def _confirmed(run: dict) -> set[str]:
    """Подтверждённая находка — запись в findings; градация тут не важна.

    `indirect` вместо `proven` — понижение доказательности, а не закрытие
    атаки, поэтому в множестве подтверждённых остаются обе.
    """
    return {item["scenario_id"] for item in run.get("findings", [])}


def compare(before: dict, after: dict) -> RegressionDiff:
    was, now = _confirmed(before), _confirmed(after)
    smoke = after.get("smoke", [])
    per_attack = {sid: (REMAINED if sid in now else CLOSED) for sid in was}
    per_attack.update({sid: APPEARED for sid in now - was})
    return RegressionDiff(
        per_attack=per_attack,
        asr_before=float(before.get("asr_percent", 0.0)),
        asr_after=float(after.get("asr_percent", 0.0)),
        smoke_ok=(all(item.get("ok") for item in smoke) if smoke else None),
        smoke_checked=len(smoke),
    )
