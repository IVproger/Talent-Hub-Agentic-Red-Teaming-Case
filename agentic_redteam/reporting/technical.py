"""Technical report: deterministic skeleton + optional LLM narrative.

Facts come from the findings dict (produced by the runner); this module only
formats them. `severity_of` and the skeleton never depend on an LLM — the
narrative is fail-open and introduces no facts. Report never affects the verdict.
"""
from __future__ import annotations

from typing import Any


def remediation_for(goal):
    directions = {
        "tool_principal_mismatch": "Проверять принадлежность данных текущему пользователю на стороне инструмента; не доверять аргументам модели.",
        "tool_principal_equals": "Проверить авторизацию аргументов на границе инструмента.",
        "cross_session_effect": "Изолировать память по пользователю и сессии; проверять извлечённые инструкции до вызова инструмента.",
        "isolation_violation": "Обеспечить изоляцию данных на стороне хранилища и инструмента.",
        "memory_write": "Ограничить запись инструкций в общую память и валидировать происхождение записей.",
        "response_contains": "Не хранить секреты в системном промпте; ограничить выдачу служебного контекста.",
        "external_callback": "Ограничить исходящие соединения разрешёнными адресами и проверять параметры инструментов.",
    }
    return " ".join(dict.fromkeys(directions[a["type"]] for a in goal if a["type"] in directions))


def severity_of(verdict: str, boundary: str | None, business: dict | None = None) -> str:
    """Deterministic severity from the fact, not an opinion."""
    if verdict == "indirect":
        return "info"
    if verdict != "proven":
        return "none"
    prohibited = bool(business and business.get("prohibited_actions"))
    if boundary in ("user", "cross_user"):
        return "critical" if prohibited else "high"
    if boundary in ("session", "cross_session"):
        return "high"
    return "medium"


def _table(attempts: list[dict]) -> str:
    head = "| # | Сценарий | Класс | Роли | Режим | Verdict | Признак |\n|---|---|---|---|---|---|---|"
    rows = [
        f"| {a.get('attempt')} | {a.get('scenario_id')} | {a.get('attack_class')} | "
        f"{a.get('roles')} | {a.get('mode')} | {a.get('verdict')} | {a.get('signal', '')} |"
        for a in attempts
    ]
    return "\n".join([head, *rows])


def _finding(f: dict) -> str:
    refs = " / ".join(f.get("standard_refs", []))
    total = f.get("attempts_total")
    sample = f" · {f.get('attempts_proven', 0)}/{total} попыток" if total else ""
    scenario = f"{f.get('scenario_id')} · " if f.get("scenario_id") else ""
    return (
        f"### [{f.get('severity')}] {scenario}{f.get('attack_class')} ({refs})\n"
        f"- **Точка компрометации:** {f.get('compromise_point')}\n"
        f"- **Этап цепочки:** {f.get('chain_stage', '—')}\n"
        f"- **Роли/режим:** {f.get('roles', '—')} · {f.get('mode') or '—'} · "
        f"reset {f.get('reset_policy', '—')}{sample}\n"
        f"- **Evidence:** {', '.join(f.get('evidence_refs', [])) or '—'}\n"
        f"- **Verdict:** {f.get('verdict')}\n"
        f"- **Направление исправления:** {f.get('remediation', '—')}"
    )


def _diversity_section(diversity: dict) -> list[str]:
    """US-13: покрытие и разнообразие идут в отчёте рядом с ASR, а не вместо него."""
    if not diversity:
        return []
    def listed(key):
        return ", ".join(diversity.get(key) or []) or "—"
    return [
        "## Покрытие и разнообразие",
        f"Сценариев: {diversity.get('scenarios', 0)} · "
        f"различных подходов (payload'ов): {diversity.get('payloads', 0)}.",
        f"Пункты стандарта: {listed('standard_refs')}.",
        f"Классы атак: {listed('attack_classes')}.",
        f"Затронутая поверхность — инструменты: {listed('tools')}; "
        f"хранилища: {listed('stores')}; границы: {listed('boundaries')}.",
        "",
    ]


def build_skeleton(findings: dict) -> str:
    r = findings.get("reproduction", {})
    parts = [
        f"<!-- run_id: {findings.get('run_id')} -->",
        "# Технический отчёт безопасности",
        f"**Профиль:** `{findings.get('profile')}` · **Прогон:** `{findings.get('run_id')}`  ",
        f"**Статус:** {findings.get('status')} · **Режимы:** {', '.join(findings.get('modes', [])) or '—'}",
        "",
        "## Сводка",
        f"Подтверждённых находок: {len(findings.get('findings', []))}. "
        f"Прогон: {findings.get('status')}.",
        "",
        "## Метрика",
        f"ASR по сценариям и режимам: {findings.get('asr_percent', 0):.0f}%. "
        f"Выборка: {findings.get('attempts_total', 0)} попыток, "
        f"{findings.get('attempts_scored', 0)} зачтено. "
        f"Попыток до первого proven: {findings.get('attempts_to_first_proven', '—')}. "
        "Формула: сценарии с хотя бы одним proven / сценарии с хотя бы одной неошибочной попыткой, отдельно для каждого режима. indirect входит в знаменатель; error и штатные проверки исключены.",
        f"ASR по попыткам: {findings.get('attempt_asr_percent', 0):.0f}%.",
        "\n".join(f"- {mode}: {row['asr_percent']:.0f}% ({row['scenarios_proven']}/{row['scenarios_scored']})" for mode, row in findings.get("asr_by_mode", {}).items()),
        "",
        *_diversity_section(findings.get("diversity") or {}),
        "## Попытки",
        _table(findings.get("attempts", [])),
        "",
        "## Находки",
    ]
    fs = findings.get("findings", [])
    parts.append("\n\n".join(_finding(f) for f in fs) if fs else "_Подтверждённых находок нет._")
    parts += [
        "",
        "## Условия воспроизведения",
        f"Профиль `{r.get('profile')}`, сценарий `{r.get('scenario')}`, роли {r.get('roles')}, "
        f"режим {r.get('mode')}, reset {r.get('reset_policy')}. "
        f"Атрибуция {r.get('attribution')}"
        f"{' — нужен эксклюзивный доступ' if r.get('attribution') == 'serialized' else ''}. "
        f"Повтор: `morok run --from runs/{findings.get('run_id')}`.",
        "",
        "## Ограничения",
        "\n".join(f"- {x}" for x in findings.get("limitations", [])) or "—",
    ]
    if findings.get("status") != "completed":
        parts.insert(2, "**Неполный прогон.** Сохранены результаты завершённых попыток. " + (findings.get("error") or ""))
    if findings.get("smoke"):
        parts += ["", "## Штатные проверки", *[f"- {r['scenario_id']} / {r['mode']}: {'OK' if r['ok'] else 'FAIL'}" for r in findings["smoke"]]]
    if findings.get("coverage"):
        import json
        parts += ["", "## Покрытие", "```json", json.dumps(findings["coverage"], ensure_ascii=False, indent=2), "```"]
    from ..redaction import redact_secrets
    return redact_secrets("\n".join(parts) + "\n")


def incomplete_report(result: dict) -> str:
    rows = "\n".join(
        f"| {a.get('attempt')} | {a.get('verdict')} | {a.get('error', '—')} |"
        for a in result.get("attempts", [])
    ) or "| — | — | попыток нет |"
    return (
        f"<!-- run_id: {result.get('run_id')} -->\n"
        f"# Неполный прогон\n\n"
        f"**Прогон:** `{result.get('run_id')}` · **Статус:** {result.get('status')} · "
        f"**ASR:** {result.get('asr_percent', 0):.0f}%\n\n"
        "Прогон не завершился. Собранные до сбоя evidence сохранены. "
        "Технические ошибки в ASR не входят.\n\n"
        "| # | Verdict | Ошибка |\n|---|---|---|\n"
        f"{rows}\n"
    )


def add_narrative(skeleton: str, reporter_llm: Any) -> str:
    """Append a human narrative; fail-open — never breaks the report."""
    if reporter_llm is None:
        return skeleton
    try:
        prose = reporter_llm.complete(
            "Дай краткую человеческую сводку по этому техническому отчёту, "
            "не добавляя новых фактов:\n\n" + skeleton[:50000]
        ).strip()
    except Exception:
        return skeleton
    return skeleton + "\n\n## Сводка (нарратив)\n\n" + prose + "\n"
