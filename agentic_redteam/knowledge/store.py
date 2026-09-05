"""База знаний о проведённых атаках: sqlite, производна от runs/."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .ingest import attacks_from_run

ATTACK_FIELDS = (
    "id", "campaign_run_id", "profile_name", "profile_version",
    "scenario_id", "attack_class", "standard_refs", "payload", "payload_tokens",
    "roles", "mode", "verdict", "severity", "compromise_point", "chain_stage",
    "signal", "evidence_refs", "created_at",
)
_JSON_FIELDS = ("standard_refs", "payload_tokens", "evidence_refs")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attacks (
  id TEXT PRIMARY KEY, campaign_run_id TEXT,
  profile_name TEXT, profile_version TEXT,
  scenario_id TEXT, attack_class TEXT, standard_refs TEXT,
  payload TEXT, payload_tokens TEXT,
  roles TEXT, mode TEXT,
  verdict TEXT, severity TEXT, compromise_point TEXT, chain_stage TEXT,
  signal TEXT, evidence_refs TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_profile ON attacks(profile_name, profile_version);
"""


class KnowledgeStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, attack: dict) -> None:
        row = {field: attack.get(field) for field in ATTACK_FIELDS}
        for field in _JSON_FIELDS:
            row[field] = json.dumps(row.get(field) or [], ensure_ascii=False)
        placeholders = ", ".join("?" for _ in ATTACK_FIELDS)
        self._conn.execute(
            f"INSERT OR REPLACE INTO attacks ({', '.join(ATTACK_FIELDS)}) VALUES ({placeholders})",
            [row[field] for field in ATTACK_FIELDS],
        )
        self._conn.commit()

    def _rows(self, where: str, params: tuple) -> list[dict]:
        cursor = self._conn.execute(f"SELECT * FROM attacks WHERE {where}", params)
        result = []
        for raw in cursor.fetchall():
            item = dict(raw)
            for field in _JSON_FIELDS:
                item[field] = json.loads(item[field]) if item[field] else []
            result.append(item)
        return result

    def all_for(self, profile_name: str) -> list[dict]:
        return self._rows("profile_name = ?", (profile_name,))

    def payloads_for(self, profile_name: str) -> list[str]:
        cursor = self._conn.execute(
            "SELECT DISTINCT payload FROM attacks WHERE profile_name = ? AND payload IS NOT NULL",
            (profile_name,))
        return [row[0] for row in cursor.fetchall()]

    def search(self, contains: str) -> list[dict]:
        like = f"%{contains}%"
        return self._rows("payload LIKE ? OR attack_class LIKE ?", (like, like))

    def close(self) -> None:
        self._conn.close()

    def record_run(self, run_dir) -> int:
        attacks = attacks_from_run(run_dir)
        for attack in attacks:
            self.record(attack)
        return len(attacks)

    def rebuild_from_runs(self, runs_root) -> int:
        total = 0
        for run_dir in sorted(Path(runs_root).iterdir()):
            if run_dir.is_dir() and (run_dir / "campaign.json").is_file():
                total += self.record_run(run_dir)
        return total
