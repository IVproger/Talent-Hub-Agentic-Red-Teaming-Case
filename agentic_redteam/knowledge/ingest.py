"""Каталог прогона → записи-атаки. Источник payload'а — transcript.jsonl.

Спек §1 упоминает knowledge.jsonl, но big-bang его удалил; актуальный
per-attempt артефакт — transcript.jsonl. База лишь индексирует runs/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..generation.dedup import tokens

_RUN_TS = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _created_at(run_id: str) -> str:
    match = _RUN_TS.match(run_id or "")
    if not match:
        return ""
    y, mo, d, h, mi, s = match.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}"


def attacks_from_run(run_dir: str | Path) -> list[dict]:
    run = Path(run_dir)
    campaign = _read_json(run / "campaign.json")
    run_id = campaign.get("run_id", run.name)
    name, _, version = str(campaign.get("profile", "")).partition("@")
    scenarios = {s["id"]: s for s in campaign.get("scenarios", []) if isinstance(s, dict)}
    findings = {}
    findings_path = run / "findings.json"
    if findings_path.is_file():
        for finding in _read_json(findings_path).get("findings", []):
            findings.setdefault(finding.get("scenario_id"), []).append(finding)
    trace_refs = []
    obs_path = run / "observability.json"
    if obs_path.is_file():
        trace_id = _read_json(obs_path).get("trace_id")
        if trace_id:
            trace_refs = [trace_id]
    created_at = _created_at(run_id)
    attacks = []
    transcript = run / "transcript.jsonl"
    for line in (transcript.read_text(encoding="utf-8").splitlines() if transcript.is_file() else []):
        if not line.strip():
            continue
        row = json.loads(line)
        scenario_id = row.get("scenario_id")
        scen = scenarios.get(scenario_id, {})
        finding = next((f for f in findings.get(scenario_id, [])
                        if f.get("verdict") == row.get("verdict")), None)
        outcomes = row.get("outcomes") or []
        attacks.append({
            "id": f"{run_id}:{scenario_id}:{row.get('attempt')}",
            "campaign_run_id": run_id,
            "profile_name": name, "profile_version": version,
            "scenario_id": scenario_id,
            "attack_class": scen.get("attack_class"),
            "standard_refs": scen.get("standard_refs", []),
            "payload": row.get("payload"),
            "payload_tokens": sorted(tokens(row.get("payload") or "")),
            "roles": row.get("actor"), "mode": row.get("mode"),
            "verdict": row.get("verdict"),
            "severity": finding.get("severity") if finding else None,
            "compromise_point": finding.get("compromise_point") if finding else None,
            "chain_stage": finding.get("chain_stage") if finding else None,
            "signal": (outcomes[0].get("detail") if outcomes else "") or "",
            "evidence_refs": list(row.get("evidence_refs") or []) + trace_refs,
            "created_at": created_at,
        })
    return attacks
