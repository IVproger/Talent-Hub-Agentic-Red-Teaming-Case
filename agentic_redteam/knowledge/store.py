"""База знаний о проведённых атаках: sqlite, производна от runs/."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .ingest import attacks_from_run

# US-36: судьба находки. Прогон даёт `confirmed` — находка доказана
# состоянием; дальше её двигает человек, а `retested` — повтор из E8.
STATUSES = ("open", "confirmed", "reported", "fixed", "retested", "closed", "reopened")
DEFAULT_STATUS = "confirmed"


class UnknownStatus(ValueError):
    pass


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
  signal TEXT, evidence_refs TEXT, created_at TEXT,
  status TEXT NOT NULL DEFAULT '{default}'
);
CREATE INDEX IF NOT EXISTS ix_profile ON attacks(profile_name, profile_version);
CREATE TABLE IF NOT EXISTS status_history (
  attack_id TEXT NOT NULL, status TEXT NOT NULL, note TEXT, at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_history ON status_history(attack_id);
""".format(default=DEFAULT_STATUS)


class KnowledgeStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """База, наполненная до US-36, получает статус, а не ломается."""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(attacks)")}
        if "status" not in columns:
            self._conn.execute(
                f"ALTER TABLE attacks ADD COLUMN status TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}'")

    def record(self, attack: dict) -> None:
        row = {field: attack.get(field) for field in ATTACK_FIELDS}
        for field in _JSON_FIELDS:
            row[field] = json.dumps(row.get(field) or [], ensure_ascii=False)
        placeholders = ", ".join("?" for _ in ATTACK_FIELDS)
        # Реиндексация runs/ идемпотентна и не должна стирать судьбу находки,
        # поэтому статус переносится из уже сохранённой записи.
        known = self._conn.execute(
            "SELECT status FROM attacks WHERE id = ?", (row["id"],)).fetchone()
        self._conn.execute(
            f"INSERT OR REPLACE INTO attacks ({', '.join(ATTACK_FIELDS)}, status) "
            f"VALUES ({placeholders}, ?)",
            [row[field] for field in ATTACK_FIELDS]
            + [known["status"] if known else DEFAULT_STATUS],
        )
        if known is None:
            self._append_history(row["id"], DEFAULT_STATUS, "")
        self._conn.commit()

    def _append_history(self, attack_id: str, status: str, note: str) -> None:
        self._conn.execute(
            "INSERT INTO status_history (attack_id, status, note, at) VALUES (?, ?, ?, ?)",
            (attack_id, status, note, datetime.now(UTC).isoformat()),
        )

    def set_status(self, attack_id: str, status: str, note: str = "") -> dict:
        if status not in STATUSES:
            raise UnknownStatus(
                f"Неизвестный статус: {status}. Допустимые: {', '.join(STATUSES)}.")
        if self._conn.execute("SELECT 1 FROM attacks WHERE id = ?", (attack_id,)).fetchone() is None:
            raise KeyError(f"В базе знаний нет находки {attack_id}.")
        self._conn.execute("UPDATE attacks SET status = ? WHERE id = ?", (status, attack_id))
        self._append_history(attack_id, status, note)
        self._conn.commit()
        return self.get(attack_id)

    def get(self, attack_id: str) -> dict:
        rows = self._rows("id = ?", (attack_id,))
        if not rows:
            raise KeyError(f"В базе знаний нет находки {attack_id}.")
        return rows[0]

    def status_history(self, attack_id: str) -> list[dict]:
        return [dict(row) for row in self._conn.execute(
            "SELECT status, note, at FROM status_history WHERE attack_id = ? ORDER BY rowid",
            (attack_id,))]

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

    def all_for_run(self, campaign_run_id: str) -> list[dict]:
        return self._rows("campaign_run_id = ?", (campaign_run_id,))

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
        """Переналить базу из runs/: она производна от прогонов, а не автономна.

        Записи, чьего прогона в `runs/` больше нет, удаляются — иначе база
        копит мусор (например, от прогонов во временных каталогах) и кормит им
        дедуп и prior-контекст генератора. Статусы находок переживают
        реиндексацию: их переносит `record` (US-36).
        """
        total, current = 0, set()
        for run_dir in sorted(Path(runs_root).iterdir()):
            if run_dir.is_dir() and (run_dir / "campaign.json").is_file():
                attacks = attacks_from_run(run_dir)
                for attack in attacks:
                    self.record(attack)
                    current.add(attack["id"])
                total += len(attacks)
        # Живой список складываем во временную таблицу: NOT IN по пустому
        # множеству в SQL даёт NULL, а не истину, и длинный IN упирается в
        # лимит параметров.
        self._conn.execute("CREATE TEMP TABLE IF NOT EXISTS keep (id TEXT PRIMARY KEY)")
        self._conn.execute("DELETE FROM keep")
        self._conn.executemany("INSERT OR IGNORE INTO keep (id) VALUES (?)",
                               [(item,) for item in current])
        self._conn.execute(
            "DELETE FROM status_history WHERE attack_id NOT IN (SELECT id FROM keep)")
        self._conn.execute("DELETE FROM attacks WHERE id NOT IN (SELECT id FROM keep)")
        self._conn.commit()
        return total
