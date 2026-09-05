"""Technical report: deterministic skeleton + optional LLM narrative.

Facts come from the findings dict (produced by the runner); this module only
formats them. `severity_of` and the skeleton never depend on an LLM — the
narrative is fail-open and introduces no facts. Report never affects the verdict.
"""
from __future__ import annotations

from typing import Any


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
        f"ASR по попыткам: {findings.get('asr_percent', 0):.0f}%. "
        f"Выборка: {findings.get('attempts_total', 0)} попыток, "
        f"{findings.get('attempts_scored', 0)} зачтено. "
        f"Попыток до первого proven: {findings.get('attempts_to_first_proven', '—')}. "
        "Формула: proven / (proven + not_proven).",
        "",
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
    return "\n".join(parts) + "\n"


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
            "не добавляя новых фактов:\n\n" + skeleton
        ).strip()
    except Exception:
        return skeleton
    return skeleton + "\n\n## Сводка (нарратив)\n\n" + prose + "\n"
