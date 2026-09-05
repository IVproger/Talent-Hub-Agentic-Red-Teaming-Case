"""Deterministic business-risk report built only from proven findings.

The agent team supplies benefits and prohibited actions in ``profile.business``.
MOROK never invents financial impact.  Optional LLM prose may rephrase the
deterministic skeleton, but cannot add facts or affect technical findings.
"""
from __future__ import annotations

from typing import Any

from ..redaction import redact_secrets


def _cell(value: Any) -> str:
    text = str(value or "—").replace("\n", " ").replace("|", "\\|")
    return " ".join(text.split())


def _explicit_match(finding: dict, action: dict) -> bool:
    checks = {
        "scenario_ids": finding.get("scenario_id"),
        "attack_classes": finding.get("attack_class"),
        "boundaries": finding.get("boundary"),
    }
    for field, actual in checks.items():
        declared = action.get(field) or []
        if declared and actual in declared:
            return True
    declared_refs = set(action.get("standard_refs") or [])
    return bool(declared_refs & set(finding.get("standard_refs") or []))


def _action_for(finding: dict, prohibited: list[dict]) -> tuple[dict | None, str]:
    matches = [item for item in prohibited if _explicit_match(finding, item)]
    if len(matches) == 1:
        return matches[0], "подтверждено явной привязкой профиля"
    if len(matches) > 1:
        return matches[0], "предположительно: совпало несколько запретов"
    if len(prohibited) == 1:
        return prohibited[0], "предположительно: в профиле задан один запрет"
    return None, "не сопоставлено — нужна привязка в профиле"


def _benefits(action: dict | None, intended: list[dict]) -> str:
    if not intended:
        return "не задана"
    ids = set((action or {}).get("effect_ids") or [])
    selected = [item for item in intended if not ids or item.get("id") in ids]
    statements = [item.get("statement") for item in selected if item.get("statement")]
    if not statements:
        return "не сопоставлена"
    prefix = "заявленная польза" if ids else "контекст пользы; явной привязки нет"
    return prefix + ": " + "; ".join(statements)


def build_business_report(findings: dict, business: dict, reporter_llm=None) -> str:
    """Render E9 without turning assumptions or non-proven attempts into facts."""
    business = business or {}
    intended = list(business.get("intended_effects") or [])
    prohibited = list(business.get("prohibited_actions") or [])
    proven = [item for item in findings.get("findings", []) if item.get("verdict") == "proven"]

    parts = [
        f"<!-- run_id: {findings.get('run_id')} -->",
        "# Бизнес-отчёт о рисках",
        "",
        f"**Профиль:** `{findings.get('profile', '—')}` · "
        f"**Прогон:** `{findings.get('run_id', '—')}`",
        "",
        "## Сводка рисков",
        f"Подтверждённых технических находок: {len(proven)}. "
        f"Заявленных полезных эффектов: {len(intended)}. "
        f"Заявленных запрещённых действий: {len(prohibited)}.",
    ]
    if not intended and not prohibited:
        parts += [
            "",
            "**Бизнес-эффекты не заданы.** MOROK не сопоставляет последствия и "
            "не оценивает ущерб без входа от команды агента.",
        ]

    parts += [
        "",
        "## Риск / польза / следующий шаг",
        "| Находка | Затронутый запрет | Возможное последствие | Польза функции | Следующий шаг | Достоверность | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    if not proven:
        parts.append("| Подтверждённых находок нет | — | — | — | — | — | — |")
    for finding in proven:
        action, confidence = _action_for(finding, prohibited)
        action_text = (action or {}).get("statement") or "не сопоставлен"
        consequence = (action or {}).get("consequence")
        if not consequence and action:
            consequence = "Нарушение заявленного запрета: " + action_text
        consequence = consequence or "не определено командой агента"
        evidence = ", ".join(finding.get("evidence_refs") or []) or "—"
        name = f"[{finding.get('severity', '—')}] {finding.get('scenario_id') or finding.get('attack_class', '—')}"
        next_step = "исправить контроль · ограничить функцию · принять риск владельцем"
        parts.append(
            "| " + " | ".join(_cell(value) for value in (
                name, action_text, consequence, _benefits(action, intended),
                next_step, confidence, evidence,
            )) + " |"
        )

    parts += [
        "",
        "## Достоверность и ограничения",
        "В отчёт включены только находки с verdict `proven`. Предположительные "
        "сопоставления помечены явно. Результаты учебного стенда нельзя автоматически "
        "переносить на продуктивную систему.",
        "Финансовый ущерб не рассчитывается: таких входных данных профиль не предоставляет.",
        "",
        "## Варианты решения",
        "- **Исправить:** усилить технический контроль и повторить regression-набор.",
        "- **Ограничить функциональность:** сузить инструменты, данные, роли или область памяти.",
        "- **Принять риск:** зафиксировать решение владельца риска и условия мониторинга.",
    ]
    skeleton = redact_secrets("\n".join(parts) + "\n")
    if reporter_llm is None:
        return skeleton
    try:
        narrative = reporter_llm.complete(
            "Кратко переформулируй этот бизнес-отчёт по-русски. Не добавляй "
            "факты, суммы ущерба или бизнес-эффекты:\n\n" + skeleton[:50000]
        ).strip()
    except Exception:
        return skeleton
    return skeleton + "\n## Краткий нарратив\n\n" + narrative + "\n"
