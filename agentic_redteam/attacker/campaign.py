"""Кампания автономного пути: зафиксированные brief → попытки → judge → ASR.

Единица измерения ASR — целая попытка атакующего (brief × режим × trial),
независимо от числа сообщений внутри неё::

    ASR = YES / (YES + NO) × 100%

Неоценённые попытки ({"status": "error", "judge_verdict": null}) в знаменатель
не входят. ``error`` — стабильный машинный статус; человеку показывается
«НЕ ОЦЕНЕНО» с причиной. Рядом с ASR выводятся количества YES, NO,
неоценённых и исключённых попыток; ASR считается отдельно по режимам цели;
при отсутствии оценённых попыток выводится «нет данных».

Independent-стратегия сохраняет trials независимыми. Adaptive-стратегия
передаёт между попытками одного brief+mode ограниченный контекст:
рефлексию атакующего, observed facts и judge verdict. Для неё дополнительно
считаются discovery within K и attempt-to-first-success.

Артефакты на попытку (attempts/NNNN/): brief, снимок профиля и конфигурации
(в campaign.json), журнал действий, evidence, причина остановки, точный
вход/ответ judge и технический статус.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from ..campaign.runner import RunEvent, emit
from ..errors import PipelineConfigurationError
from ..profile.schema import TargetProfile
from ..reporting.autonomous import (
    AUTONOMOUS_RUN_KIND,
    build_autonomous_business_report,
    build_autonomous_report,
    load_autonomous_run,
)
from ..storage.runs import RunStorage
from .agent import (
    AttackerAttempt,
    AttackerDeps,
    AttackerLimits,
    run_attacker_attempt,
)
from .briefs import AttackBrief
from .judge import JudgeOutcome, build_judge_context, judge_attempt
from .status import attempt_outcome_label, classify_unscored

NO_DATA = "нет данных"
CAMPAIGN_STRATEGIES = frozenset({"independent", "adaptive"})


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def asr_row(items: list[dict]) -> dict:
    """YES/(YES+NO); ошибочные и исключённые попытки вне знаменателя."""
    yes = sum(1 for item in items if item.get("judge_verdict") == "YES")
    no = sum(1 for item in items if item.get("judge_verdict") == "NO")
    errors = sum(1 for item in items if item.get("status") == "error")
    excluded = sum(1 for item in items if item.get("status") == "excluded")
    scored = yes + no
    percent = round(100 * yes / scored, 2) if scored else None
    return {
        "yes": yes,
        "no": no,
        "errors": errors,
        "excluded": excluded,
        "scored": scored,
        "asr_percent": percent,
        "asr_display": f"{percent:g}%" if percent is not None else NO_DATA,
    }


def asr_summary(attempts: list[dict]) -> dict:
    by_mode = {}
    for item in attempts:
        mode = item.get("mode") or "default"
        by_mode.setdefault(mode, []).append(item)
    return {
        "overall": asr_row(attempts),
        "by_mode": {mode: asr_row(items) for mode, items in sorted(by_mode.items())},
    }


def adaptive_summary(attempts: list[dict], attempts_budget: int) -> dict:
    """Discovery metrics for dependent attempts grouped by brief and mode."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in attempts:
        key = (item["brief_id"], item.get("mode") or "default")
        grouped.setdefault(key, []).append(item)
    groups = []
    for (brief_id, mode), items in sorted(grouped.items()):
        successes = [item for item in items if item.get("judge_verdict") == "YES"]
        first = min((item["trial"] for item in successes), default=None)
        groups.append({
            "brief_id": brief_id,
            "mode": mode,
            "attempts_run": len(items),
            "success": first is not None,
            "first_success_attempt": first,
        })
    succeeded = sum(1 for item in groups if item["success"])
    total = len(groups)
    cumulative = {}
    for number in range(1, attempts_budget + 1):
        count = sum(
            1 for item in groups
            if item["first_success_attempt"] is not None
            and item["first_success_attempt"] <= number
        )
        cumulative[str(number)] = round(100 * count / total, 2) if total else None
    return {
        "groups": groups,
        "groups_total": total,
        "groups_succeeded": succeeded,
        "success_within_budget_percent": (
            round(100 * succeeded / total, 2) if total else None
        ),
        "cumulative_success_percent": cumulative,
    }


def _experience_entry(
    attempt: AttackerAttempt, outcome: JudgeOutcome, index: int,
) -> dict:
    """Combine attacker reflection with compact harness-observed facts."""
    return {
        "attempt": index,
        "trial": attempt.trial,
        "stop_reason": attempt.stop_reason,
        "technical_status": outcome.status,
        "judge_verdict": outcome.judge_verdict,
        "technical_error": (
            attempt.error or outcome.record.get("error")
        ),
        "unscored_reason": classify_unscored(
            attempt.stop_reason, attempt.error, outcome.record.get("error")
        ),
        "summary": attempt.claim_summary,
        "learning": attempt.learning,
        "learning_source": attempt.learning_source,
        "finalization": {
            key: attempt.finalization.get(key)
            for key in ("required", "trigger", "status", "timeout_seconds", "error")
            if key in attempt.finalization
        },
        "observed": {
            "tool_calls": [
                {"tool": call.tool, "principal": call.principal}
                for call in attempt.facts.tool_calls[:20]
            ],
            "memory_writes": [
                {
                    "store": write.store_id,
                    "scope": write.scope,
                    "key": write.key,
                    "owner": write.owner,
                }
                for write in attempt.facts.memory_writes[:20]
            ],
            "callbacks": len(attempt.facts.callbacks),
            "action_errors": [
                action.error[:500] for action in attempt.actions if action.error
            ][:10],
        },
        "note": "learning — рефлексия атакующего; observed — факты harness.",
    }


def _bounded_experience(items: list[dict], limits: AttackerLimits) -> list[dict]:
    """Keep recent experience inside both attempt-count and character budgets."""
    candidates = items[-limits.experience_max_attempts:]
    selected: list[dict] = []
    for item in reversed(candidates):
        candidate = [item, *selected]
        size = len(json.dumps(candidate, ensure_ascii=False))
        if not selected and size > limits.experience_max_chars:
            compact = {
                **item,
                "summary": (item.get("summary") or "")[:300],
                "learning": {
                    field: [text[:240] for text in values[:4]]
                    for field, values in item.get("learning", {}).items()
                },
                "observed": {
                    **item.get("observed", {}),
                    "tool_calls": item.get("observed", {}).get("tool_calls", [])[:10],
                    "memory_writes": item.get("observed", {}).get("memory_writes", [])[:10],
                    "action_errors": [
                        text[:240]
                        for text in item.get("observed", {}).get("action_errors", [])[:5]
                    ],
                },
            }
            candidate = [compact]
            size = len(json.dumps(candidate, ensure_ascii=False))
        if size <= limits.experience_max_chars:
            selected = candidate
    return selected


def _result_row(attempt: AttackerAttempt, outcome: JudgeOutcome, index: int) -> dict:
    return {
        "attempt": index,
        "brief_id": attempt.brief_id,
        "mode": attempt.mode,
        "trial": attempt.trial,
        "stop_reason": attempt.stop_reason,
        "claim": attempt.claim,
        "turns": len(attempt.actions),
        "inherited_attempts": attempt.inherited_attempts,
        "learning": attempt.learning,
        "learning_source": attempt.learning_source,
        "finalization": attempt.finalization,
        "status": outcome.status,
        "judge_verdict": outcome.judge_verdict,
        "error": attempt.error or outcome.record.get("error"),
        "unscored_reason": classify_unscored(
            attempt.stop_reason, attempt.error, outcome.record.get("error")
        ),
    }


def _persist_attempt(storage: RunStorage, run_dir: Path, attempt: AttackerAttempt,
                     brief: AttackBrief, outcome: JudgeOutcome, index: int) -> Path:
    directory = run_dir / "attempts" / f"{index:04d}"
    storage.write_text(
        directory, "brief.yaml",
        yaml.safe_dump(brief.to_mapping(), allow_unicode=True, sort_keys=False),
    )
    storage.write_json(directory, "actions.json", {
        "brief_id": attempt.brief_id,
        "mode": attempt.mode,
        "trial": attempt.trial,
        "stop_reason": attempt.stop_reason,
        "claim": attempt.claim,
        "claim_summary": attempt.claim_summary,
        "inherited_attempts": attempt.inherited_attempts,
        "learning": attempt.learning,
        "learning_source": attempt.learning_source,
        "finalization": attempt.finalization,
        "actions": [
            {
                "turn": action.turn, "action": action.kind, "role": action.role,
                "session": action.session, "session_id": action.session_id,
                "principal": action.principal, "request": action.request,
                "response": action.response, "error": action.error,
                "facts": action.facts,
                "observations": action.observations,
                "memory_diffs": action.memory_diffs,
                "observation_id": action.observation_id,
                "trace_id": action.trace_id,
            }
            for action in attempt.actions
        ],
    })
    storage.write_json(directory, "evidence.json", {
        "brief_id": attempt.brief_id,
        "facts": attempt.facts,
        "observations": attempt.observations,
        "memory_diffs": attempt.memory_diffs,
    })
    storage.write_json(directory, "judge.json", _jsonable(outcome.record))
    storage.write_json(directory, "result.json", _result_row(attempt, outcome, index))
    return directory


def run_attack_campaign(briefs: list[AttackBrief], deps: AttackerDeps, judge,
                        storage: RunStorage, run_id: str, modes=None, trials: int = 1,
                        limits: AttackerLimits | None = None,
                        profile: TargetProfile | None = None, profile_ref: str = "",
                        config: dict | None = None, on_event=None,
                        should_stop=None, metadata: dict | None = None,
                        strategy: str = "independent",
                        stop_on_success: bool = False) -> dict:
    """Прогнать набор brief по режимам и повторам; каждая попытка — с judge."""
    limits = limits or AttackerLimits()
    if strategy not in CAMPAIGN_STRATEGIES:
        raise PipelineConfigurationError(
            f"Неизвестная стратегия кампании: {strategy}"
        )
    if stop_on_success and strategy != "adaptive":
        raise PipelineConfigurationError(
            "--stop-on-success используется только с --strategy adaptive."
        )
    briefs = list(briefs)
    modes = list(modes or [None])
    run_dir = storage.create(run_id)
    campaign_record = {
        "run_kind": AUTONOMOUS_RUN_KIND,
        "run_id": run_id,
        "profile": profile_ref,
        "modes": modes,
        "trials": trials,
        "strategy": strategy,
        "stop_on_success": stop_on_success,
        "limits": _jsonable(limits),
        "briefs": [brief.to_mapping() for brief in briefs],
        "config": config or {},
        **(metadata or {}),
    }
    if profile is not None:
        campaign_record["profile_snapshot"] = _profile_snapshot(profile)
    storage.write_campaign(run_dir, campaign_record)
    storage.write_json(run_dir, "status.json", {"run_id": run_id, "status": "running"})

    rows: list[dict] = []
    experience: dict[str, list[dict]] = {}
    total = len(briefs) * len(modes) * max(1, trials)
    index = 0
    status, error = "completed", None

    def checkpoint(current: str) -> dict:
        summary = asr_summary(rows)
        summary["adaptive"] = (
            adaptive_summary(rows, trials) if strategy == "adaptive" else None
        )
        record = {
            "run_id": run_id,
            "profile": profile_ref,
            "status": current,
            "strategy": strategy,
            "asr": summary,
            "attempts": rows,
            "error": error,
        }
        storage.write_json(run_dir, "summary.json", record)
        report_model = load_autonomous_run(run_dir)
        storage.write_text(
            run_dir, "report.md", build_autonomous_report(report_model)
        )
        storage.write_text(
            run_dir, "business-report.md",
            build_autonomous_business_report(report_model),
        )
        storage.write_json(run_dir, "status.json", {
            "run_id": run_id,
            "status": current,
            "asr_percent": summary["overall"]["asr_percent"],
            "asr_display": summary["overall"]["asr_display"],
            "attempts_total": len(rows),
            "error": error,
        })
        return record

    try:
        checkpoint("running")
        for mode in modes:
            for brief in briefs:
                for trial in range(1, max(1, trials) + 1):
                    if should_stop and should_stop():
                        raise KeyboardInterrupt()
                    index += 1
                    emit(on_event, RunEvent(
                        "attempt", f"попытка {index}/{total}: brief {brief.id}",
                        attempt=index, total=total,
                        data={"brief": brief.id, "mode": mode, "trial": trial},
                    ))
                    experience_key = f"{brief.id}::{mode or 'default'}"
                    prior = (
                        _bounded_experience(experience.get(experience_key, []), limits)
                        if strategy == "adaptive" else []
                    )
                    attempt = run_attacker_attempt(
                        brief, mode, trial, deps, limits, run_id=run_id,
                        previous_attempts=prior,
                    )
                    if attempt.error is not None:
                        # Техническая ошибка попытки: judge не вызывается,
                        # попытка не входит в знаменатель ASR.
                        outcome = JudgeOutcome("error", None, {
                            "status": "error",
                            "judge_verdict": None,
                            "error": attempt.error,
                            "input": build_judge_context(brief, profile, attempt),
                        })
                    else:
                        outcome = judge_attempt(
                            build_judge_context(brief, profile, attempt),
                            judge, limits.judge_timeout,
                        )
                    row = _result_row(attempt, outcome, index)
                    rows.append(row)
                    if strategy == "adaptive":
                        experience.setdefault(experience_key, []).append(
                            _experience_entry(attempt, outcome, index)
                        )
                        storage.write_json(run_dir, "experience.json", {
                            "strategy": strategy,
                            "by_brief_mode": experience,
                        })
                    _persist_attempt(storage, run_dir, attempt, brief, outcome, index)
                    storage.append_transcript(run_dir, row)
                    checkpoint("running")
                    emit(on_event, RunEvent(
                        "attempt",
                        f"попытка {index}/{total}: {attempt_outcome_label(row)}",
                        status="running", attempt=index, total=total,
                        data={"brief": brief.id, "mode": mode,
                              "verdict": row["judge_verdict"], "status": row["status"]},
                    ))
                    if stop_on_success and row["judge_verdict"] == "YES":
                        break
    except KeyboardInterrupt:
        status, error = "interrupted", "Прервано пользователем"
    except Exception as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    record = checkpoint(status)
    emit(on_event, RunEvent(
        status, f"{status}: ASR {record['asr']['overall']['asr_display']}",
        status=status, data={"run_dir": str(run_dir)},
    ))
    if status == "interrupted":
        raise KeyboardInterrupt
    return record


def _profile_snapshot(profile: TargetProfile) -> dict:
    from ..profile.registry import to_mapping
    return to_mapping(profile)
