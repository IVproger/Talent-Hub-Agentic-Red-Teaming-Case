"""Reports and read model for autonomous AttackBrief campaigns.

The scenario runner and the autonomous runner intentionally persist different
facts.  Scenario runs have ``findings.json``; autonomous runs have a campaign
summary plus one evidence bundle per whole attacker attempt.  This module keeps
that distinction explicit while presenting both humans and the UI with one
complete, tolerant read model.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..attacker.status import attempt_outcome_label
from ..redaction import redact_secrets
from ..storage.runs import RunStorage
from .technical import memory_diff_rows, observation_url


AUTONOMOUS_RUN_KIND = "autonomous_briefs"


def is_autonomous_run(run_dir: str | Path) -> bool:
    """Return whether a directory carries an autonomous campaign."""
    root = Path(run_dir)
    try:
        campaign = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return bool(
        isinstance(campaign, dict)
        and isinstance(summary, dict)
        and isinstance(campaign.get("briefs"), list)
        and isinstance(summary.get("asr"), dict)
    )


def load_autonomous_run(run_dir: str | Path) -> dict:
    """Load an autonomous run, including every available attempt artifact.

    Missing optional artifacts are represented honestly instead of making an
    otherwise useful interrupted run unreadable.  Malformed campaign/summary
    files remain hard errors because they define the run identity and metrics.
    """
    root = Path(run_dir).expanduser().resolve()
    storage = RunStorage(root.parent)
    campaign = storage.load_json(root, "campaign.json")
    summary = storage.load_json(root, "summary.json")
    if not (
        isinstance(campaign, dict)
        and isinstance(summary, dict)
        and isinstance(campaign.get("briefs"), list)
        and isinstance(summary.get("asr"), dict)
    ):
        raise ValueError(f"Каталог не является автономным прогоном: {root}")

    briefs = {
        str(item.get("id")): item
        for item in campaign.get("briefs", [])
        if isinstance(item, dict) and item.get("id")
    }
    summary_rows = {
        int(item["attempt"]): item
        for item in summary.get("attempts", [])
        if isinstance(item, dict) and isinstance(item.get("attempt"), int)
    }
    attempt_dirs: dict[int, Path] = {}
    attempts_root = root / "attempts"
    if attempts_root.is_dir():
        for path in attempts_root.iterdir():
            if path.is_dir() and path.name.isdigit():
                attempt_dirs[int(path.name)] = path

    attempts = []
    for number in sorted(set(summary_rows) | set(attempt_dirs)):
        directory = attempt_dirs.get(number)
        result = _optional_json(storage, directory, "result.json")
        actions = _optional_json(storage, directory, "actions.json")
        evidence = _optional_json(storage, directory, "evidence.json")
        judge = _optional_json(storage, directory, "judge.json")
        row = {**summary_rows.get(number, {}), **result}
        brief_id = str(row.get("brief_id") or actions.get("brief_id") or "")
        read_error = any(
            value.get("_read_error")
            for value in (result, actions, evidence, judge)
        )
        row.update({
            "attempt": number,
            "brief_id": brief_id,
            "brief": briefs.get(brief_id, {}),
            "claim": row.get("claim") or actions.get("claim"),
            "claim_summary": actions.get("claim_summary") or row.get("claim_summary"),
            "status": row.get("status") or judge.get("status"),
            "judge_verdict": (
                row.get("judge_verdict") or judge.get("judge_verdict")
            ),
            "error": row.get("error") or judge.get("error"),
            "learning": actions.get("learning") or row.get("learning") or {},
            "inherited_attempts": (
                actions.get("inherited_attempts")
                or row.get("inherited_attempts")
                or []
            ),
            "actions": actions.get("actions") or [],
            "evidence": evidence,
            "judge": judge,
            "artifact_dir": (
                str(directory.relative_to(root)) if directory is not None else None
            ),
            "artifact_complete": bool(
                directory is not None
                and all((directory / name).is_file() for name in (
                    "brief.yaml", "actions.json", "evidence.json",
                    "judge.json", "result.json",
                ))
                and not read_error
            ),
        })
        attempts.append(row)

    experience = _optional_json(storage, root, "experience.json")
    observability = _optional_json(storage, root, "observability.json")
    return {
        "kind": AUTONOMOUS_RUN_KIND,
        "run_dir": str(root),
        "run_id": summary.get("run_id") or campaign.get("run_id") or root.name,
        "profile": summary.get("profile") or campaign.get("profile"),
        "status": summary.get("status") or "unknown",
        "strategy": summary.get("strategy") or campaign.get("strategy") or "independent",
        "error": summary.get("error"),
        "asr": summary.get("asr") or {},
        "campaign": campaign,
        "briefs": list(briefs.values()),
        "attempts": attempts,
        "experience": experience,
        "observability": observability,
    }


def build_autonomous_report(report: dict) -> str:
    """Render a deterministic technical report from persisted attempt facts."""
    campaign = report.get("campaign") or {}
    asr = report.get("asr") or {}
    overall = asr.get("overall") or {}
    attempts = report.get("attempts") or []
    briefs = report.get("briefs") or []
    modes = [str(mode or "default") for mode in campaign.get("modes") or []]
    refs = sorted({
        str(ref) for brief in briefs for ref in brief.get("standard_refs") or []
    })
    successful = [row for row in attempts if row.get("judge_verdict") == "YES"]
    limits = campaign.get("limits") or {}
    lines = [
        f"<!-- run_id: {report.get('run_id')} -->",
        "# Технический отчёт автономной кампании",
        "",
        f"**Профиль:** `{report.get('profile') or '—'}` · "
        f"**Прогон:** `{report.get('run_id') or '—'}`  ",
        f"**Статус:** {report.get('status') or '—'} · "
        f"**Стратегия:** `{report.get('strategy') or 'independent'}` · "
        f"**Режимы:** {', '.join(modes) or 'default'}",
        "",
    ]
    if report.get("status") != "completed":
        lines += [
            "**Неполный прогон.** В отчёт включены только уже сохранённые попытки. "
            + str(report.get("error") or ""),
            "",
        ]
    lines += [
        "## Сводка",
        "",
        f"Успешных атак по независимому judge: {len(successful)}. "
        f"Оценено попыток: {overall.get('scored', 0)}; "
        f"не оценено из-за технических причин: {overall.get('errors', 0)}; "
        f"исключено: {overall.get('excluded', 0)}.",
        "",
        "## Метрика",
        "",
        "Единица измерения — полная попытка атакующего по одному brief, режиму "
        "и trial. Формула: `YES / (YES + NO)`; ошибки и исключённые попытки "
        "не входят в знаменатель.",
        "",
        "| Режим | YES | NO | Не оценено | Исключено | Оценено | ASR |",
        "|---|---:|---:|---:|---:|---:|---:|",
        _asr_line("Всего", overall),
    ]
    for mode, row in (asr.get("by_mode") or {}).items():
        lines.append(_asr_line(str(mode), row))

    adaptive = asr.get("adaptive")
    if isinstance(adaptive, dict):
        percent = adaptive.get("success_within_budget_percent")
        display = f"{percent:g}%" if isinstance(percent, (int, float)) else "нет данных"
        lines += [
            "",
            "## Adaptive discovery",
            "",
            f"Успех в пределах бюджета: {adaptive.get('groups_succeeded', 0)}/"
            f"{adaptive.get('groups_total', 0)} ({display}).",
            "",
            "| Brief | Режим | Попыток | Первый успех |",
            "|---|---|---:|---:|",
        ]
        for item in adaptive.get("groups") or []:
            lines.append("| " + " | ".join(_cell(value) for value in (
                item.get("brief_id"), item.get("mode"), item.get("attempts_run"),
                item.get("first_success_attempt"),
            )) + " |")

    lines += [
        "",
        "## Покрытие",
        "",
        f"Brief: {len(briefs)} · режимов: {len(modes) or 1} · "
        f"запланировано попыток: {len(briefs) * (len(modes) or 1) * int(campaign.get('trials') or 1)} · "
        f"сохранено: {len(attempts)}.",
        f"Пункты стандартов: {', '.join(refs) or '—'}.",
        "",
        "### Бюджеты попытки",
        "",
        "| Параметр | Значение |",
        "|---|---:|",
        *[f"| `{key}` | {_cell(value)} |" for key, value in limits.items()],
        "",
        "## Попытки",
        "",
        "| # | Brief | Режим | Trial | Ходов | Остановка | Claim | Judge | Артефакты |",
        "|---:|---|---|---:|---:|---|---|---|---|",
    ]
    if not attempts:
        lines.append("| — | — | — | — | — | — | — | — | нет |")
    for row in attempts:
        lines.append("| " + " | ".join(_cell(value) for value in (
            row.get("attempt"), row.get("brief_id"), row.get("mode") or "default",
            row.get("trial"), row.get("turns", len(row.get("actions") or [])),
            row.get("stop_reason"), row.get("claim"),
            attempt_outcome_label(row),
            "полные" if row.get("artifact_complete") else "неполные",
        )) + " |")

    lines += ["", "## Успешные атаки"]
    if successful:
        for row in successful:
            lines += [
                "",
                f"- **Попытка {row.get('attempt')} · `{row.get('brief_id')}` · "
                f"{row.get('mode') or 'default'}:** "
                f"{_inline(row.get('claim_summary') or 'judge вернул YES')}",
                f"  Evidence: `{row.get('artifact_dir') or '—'}/judge.json`, "
                f"`{row.get('artifact_dir') or '—'}/evidence.json`.",
            ]
    else:
        lines += ["", "_Judge не подтвердил ни одной успешной атаки._"]

    lines += ["", "## Детали попыток"]
    for row in attempts:
        lines += _attempt_section(row, report.get("observability") or {})

    briefs_source = (
        campaign.get("briefs_source")
        or campaign.get("briefs_dir")
        or "<briefs-path>"
    )
    profile = campaign.get("profile") or report.get("profile") or "<profile>"
    mode_arg = ",".join(str(mode) for mode in campaign.get("modes") or [] if mode)
    command = (
        f"python -m agentic_redteam run --profile {profile} --briefs {briefs_source} "
        f"--strategy {report.get('strategy') or 'independent'} "
        f"--trials {campaign.get('trials') or 1}"
    )
    if mode_arg:
        command += f" --mode {mode_arg}"
    if campaign.get("stop_on_success"):
        command += " --stop-on-success"
    lines += [
        "",
        "## Условия воспроизведения",
        "",
        f"```shell\n{command.replace('```', '` ` `')}\n```",
        "",
        "Точный профиль, effective config, ограничения, brief и все входы judge "
        "сохранены в `campaign.json` и `attempts/NNNN/`.",
        "",
        "## Ограничения",
        "",
        "- `YES`/`NO` — решение LLM-judge по сохранённому контексту, а не "
        "детерминированный state-verdict старого сценарного пути.",
        "- Рефлексия `learning` — заявление атакующего. Наблюдаемые tool calls, "
        "memory writes, callbacks и ответы цели хранятся отдельно как evidence.",
        "- ASR adaptive-кампании зависит от порядка попыток: поздняя попытка может "
        "использовать ограниченный опыт ранних.",
        "- Технические ошибки исключены из ASR и должны разбираться отдельно; "
        "они не означают защищённость цели.",
    ]
    return redact_secrets("\n".join(lines) + "\n")


def build_autonomous_business_report(report: dict, reporter_llm=None) -> str:
    """Render a conservative business view without inventing impact/severity."""
    campaign = report.get("campaign") or {}
    business = (campaign.get("profile_snapshot") or {}).get("business") or {}
    intended = list(business.get("intended_effects") or [])
    prohibited = list(business.get("prohibited_actions") or [])
    successes = [row for row in report.get("attempts") or []
                 if row.get("judge_verdict") == "YES"]
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in report.get("attempts") or []:
        key = (str(row.get("brief_id") or "—"), str(row.get("mode") or "default"))
        groups.setdefault(key, []).append(row)
    risk_rows = [
        min(items, key=lambda row: row.get("attempt", 0))
        for items in groups.values()
        if any(row.get("judge_verdict") == "YES" for row in items)
    ]
    lines = [
        f"<!-- run_id: {report.get('run_id')} -->",
        "# Бизнес-отчёт автономной кампании",
        "",
        f"**Профиль:** `{report.get('profile') or '—'}` · "
        f"**Прогон:** `{report.get('run_id') or '—'}`",
        "",
        "## Сводка рисков",
        "",
        f"Judge подтвердил успешных попыток: {len(successes)}. "
        f"Затронуто brief: {len({row.get('brief_id') for row in successes})}. "
        f"Заявленных запрещённых действий в профиле: {len(prohibited)}.",
    ]
    if not intended and not prohibited:
        lines += [
            "",
            "**Бизнес-контекст не задан.** Последствия и финансовый ущерб не "
            "оцениваются без явных данных владельца продукта.",
        ]
    lines += [
        "",
        "## Риск / контекст / следующий шаг",
        "",
        "| Brief | Режим | YES / оценено | Критерий успеха | Затронутый запрет | Последствие | Evidence | Следующий шаг |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    if not risk_rows:
        lines.append("| Подтверждённых успешных атак нет | — | — | — | — | — | — | — |")
    for row in risk_rows:
        brief = row.get("brief") or {}
        grouped = groups[(str(row.get("brief_id") or "—"),
                          str(row.get("mode") or "default"))]
        yes = sum(item.get("judge_verdict") == "YES" for item in grouped)
        scored = sum(item.get("judge_verdict") in {"YES", "NO"} for item in grouped)
        first_success = min(
            (item for item in grouped if item.get("judge_verdict") == "YES"),
            key=lambda item: item.get("attempt", 0),
        )
        action, confidence = _business_action(brief, prohibited)
        statement = (action or {}).get("statement") or "не сопоставлен"
        if action:
            statement += f" ({confidence})"
        consequence = (action or {}).get("consequence") or "не задано владельцем"
        evidence = f"{first_success.get('artifact_dir') or '—'}/judge.json"
        lines.append("| " + " | ".join(_cell(value) for value in (
            brief.get("id") or row.get("brief_id"), row.get("mode") or "default",
            f"{yes}/{scored}", brief.get("success_criteria"), statement,
            consequence, evidence,
            "исправить контроль, затем повторить brief",
        )) + " |")
    lines += [
        "",
        "## Полезные эффекты функции",
        "",
        *(
            [f"- `{item.get('id', '—')}`: {item.get('statement', '—')}"
             for item in intended]
            or ["_Не заданы в снимке профиля._"]
        ),
        "",
        "## Достоверность и ограничения",
        "",
        "- Включены только попытки с judge verdict `YES`.",
        "- Severity не вычисляется: автономный brief пока не содержит "
        "детерминированной привязки к boundary и бизнес-запрету.",
        "- Сопоставление с запретом считается явным только при пересечении "
        "`standard_refs`; остальные последствия не выводятся автоматически.",
        "- Финансовый ущерб не рассчитывается без входных данных владельца риска.",
    ]
    skeleton = redact_secrets("\n".join(lines) + "\n")
    if reporter_llm is None:
        return skeleton
    try:
        narrative = reporter_llm.complete(
            "Кратко переформулируй этот бизнес-отчёт по-русски. Не добавляй "
            "факты, severity, суммы ущерба или бизнес-эффекты:\n\n"
            + skeleton[:50000]
        ).strip()
    except Exception:
        return skeleton
    return skeleton + "\n## Краткий нарратив\n\n" + narrative + "\n"


def _optional_json(storage: RunStorage, directory: Path | None, name: str) -> dict:
    if directory is None or not (directory / name).is_file():
        return {}
    try:
        value = storage.load_json(directory, name)
    except (OSError, ValueError):
        return {"_read_error": f"Не удалось прочитать {name}"}
    return value if isinstance(value, dict) else {"_read_error": f"{name} не объект"}


def _asr_line(label: str, row: dict) -> str:
    return "| " + " | ".join(_cell(value) for value in (
        label, row.get("yes", 0), row.get("no", 0), row.get("errors", 0),
        row.get("excluded", 0), row.get("scored", 0),
        row.get("asr_display", "нет данных"),
    )) + " |"


def _attempt_section(row: dict, observability: dict) -> list[str]:
    brief = row.get("brief") or {}
    number = row.get("attempt")
    verdict = attempt_outcome_label(row)
    lines = [
        "",
        f"### Попытка {number} · `{row.get('brief_id') or '—'}` · {verdict}",
        "",
        f"- **Режим / trial:** `{row.get('mode') or 'default'}` / {row.get('trial') or '—'}",
        f"- **Остановка:** `{row.get('stop_reason') or '—'}`; "
        f"ходов: {row.get('turns', len(row.get('actions') or []))}",
        f"- **Claim атакующего:** `{row.get('claim') or '—'}` — "
        f"{_inline(row.get('claim_summary') or 'без summary')}",
        f"- **Objective:** {_inline(brief.get('objective') or '—')}",
        f"- **Success criteria:** {_inline(brief.get('success_criteria') or '—')}",
        f"- **Стандарты:** {', '.join(brief.get('standard_refs') or []) or '—'}",
        f"- **Наследованный опыт:** {', '.join(map(str, row.get('inherited_attempts') or [])) or 'нет'}",
    ]
    if row.get("error"):
        lines.append(f"- **Техническая ошибка:** {_inline(row.get('error'))}")
    if not row.get("artifact_complete"):
        lines.append("- **Артефакты:** набор неполный; доступные данные показаны ниже.")

    learning = row.get("learning") or {}
    if any(learning.values()):
        lines += ["", "#### Рефлексия атакующего"]
        labels = {
            "strategies_tried": "Что пробовал",
            "observations": "Что наблюдал",
            "hypotheses": "Гипотезы",
            "next_steps": "Что пробовать дальше",
            "avoid": "Что не повторять",
        }
        for key, label in labels.items():
            values = learning.get(key) or []
            if values:
                lines.append(f"- **{label}:** " + "; ".join(_inline(item) for item in values))

    actions = row.get("actions") or []
    lines += [
        "",
        "#### Хронология действий",
        "",
        "| Ход | Действие | Роль / principal | Сессия | Сигналы | Observation |",
        "|---:|---|---|---|---|---|",
    ]
    if not actions:
        lines.append("| — | действий нет | — | — | — | — |")
    trace_url = observability.get("trace_url")
    for action in actions:
        facts = action.get("facts") or {}
        signals = []
        for call in facts.get("tool_calls") or []:
            signals.append(f"tool {call.get('tool')} → {call.get('principal')}")
        for write in facts.get("memory_writes") or []:
            signals.append(f"memory {write.get('store_id') or write.get('store')}")
        callbacks = facts.get("callbacks") or []
        if callbacks:
            signals.append(f"callbacks {len(callbacks)}")
        if action.get("error"):
            signals.append("ошибка: " + _inline(action.get("error")))
        observation_id = action.get("observation_id")
        deep_link = observation_url(trace_url, observation_id)
        observation = (
            f"[span {observation_id}]({deep_link})" if deep_link
            else observation_id or "—"
        )
        lines.append("| " + " | ".join(_cell(value) for value in (
            action.get("turn"), action.get("action"),
            f"{action.get('role') or '—'} / {action.get('principal') or '—'}",
            action.get("session") or "—", "; ".join(signals) or "—", observation,
        )) + " |")

    for action in actions:
        if action.get("request") is None and action.get("response") is None:
            continue
        lines += [
            "",
            f"##### Ход {action.get('turn')} · `{action.get('action')}`",
            "",
            "**Запрос**",
            "",
            _fence(action.get("request")),
            "",
            "**Ответ цели**",
            "",
            _fence(action.get("response")),
        ]

    chain = [dict(action, name=f"turn-{action.get('turn')}") for action in actions]
    diff_rows = memory_diff_rows(chain)
    lines += ["", "#### Изменения памяти", ""]
    if diff_rows:
        lines += [
            "| Ход | Хранилище | Изменение | Ключ | До | После |",
            "|---|---|---|---|---|---|",
            *["| " + " | ".join(_cell(value) for value in values) + " |"
              for values in diff_rows],
        ]
    else:
        lines.append("_Подтверждённых изменений памяти нет._")

    evidence = row.get("evidence") or {}
    facts = evidence.get("facts") or {}
    lines += [
        "",
        "#### Evidence и judge",
        "",
        f"Tool calls: {len(facts.get('tool_calls') or [])}; "
        f"memory writes: {len(facts.get('memory_writes') or [])}; "
        f"callbacks: {len(facts.get('callbacks') or [])}.",
        f"Результат: `{attempt_outcome_label(row)}` · "
        f"машинный статус `{row.get('status') or '—'}`.",
        f"Локальные артефакты: `{row.get('artifact_dir') or '—'}`.",
    ]
    return lines


def _business_action(brief: dict, prohibited: list[dict]) -> tuple[dict | None, str]:
    refs = set(brief.get("standard_refs") or [])
    matched = [item for item in prohibited
               if refs & set(item.get("standard_refs") or [])]
    if len(matched) == 1:
        return matched[0], "явная привязка по standard_refs"
    if len(matched) > 1:
        return matched[0], "несколько явных совпадений; показано первое"
    return None, "нет явной привязки"


def _cell(value: Any) -> str:
    return " ".join(str(value if value not in (None, "") else "—")
                    .replace("\n", " ").replace("|", "\\|").split())


def _inline(value: Any, limit: int = 1000) -> str:
    text = " ".join(str(value or "—").split())
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return text.replace("`", "'")


def _fence(value: Any) -> str:
    text = str(value if value not in (None, "") else "—").replace("```", "` ` `")
    return f"```text\n{text}\n```"
