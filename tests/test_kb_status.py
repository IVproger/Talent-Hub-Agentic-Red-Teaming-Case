"""US-36: судьба находки — статус и его история в базе знаний.

Пока у находки нет статуса, MOROK остаётся генератором отчётов; со статусом
он становится частью процесса исправления.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from agentic_redteam.app_cli import main
from agentic_redteam.knowledge.store import STATUSES, KnowledgeStore, UnknownStatus


def attack(attack_id="run:bac:1", **overrides) -> dict:
    row = {"id": attack_id, "campaign_run_id": "run", "profile_name": "stand",
           "profile_version": "1.0.0", "scenario_id": "bac", "attack_class": "bac",
           "payload": "отрава", "verdict": "proven", "created_at": "2026-09-05T00:00:00Z"}
    row.update(overrides)
    return row


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "kb.sqlite"
        self.store = KnowledgeStore(self.path)
        self.addCleanup(self.store.close)

    def test_recorded_attack_starts_confirmed(self):
        """Находка из прогона доказана состоянием — она уже подтверждена."""
        self.store.record(attack())
        self.assertEqual(self.store.all_for("stand")[0]["status"], "confirmed")

    def test_status_moves_through_the_lifecycle(self):
        self.store.record(attack())
        for status in ("reported", "fixed", "retested", "closed"):
            self.store.set_status("run:bac:1", status)
            self.assertEqual(self.store.all_for("stand")[0]["status"], status)

    def test_unknown_status_is_refused(self):
        self.store.record(attack())
        with self.assertRaises(UnknownStatus):
            self.store.set_status("run:bac:1", "почти закрыта")

    def test_status_of_unknown_attack_is_refused(self):
        with self.assertRaises(KeyError):
            self.store.set_status("нет такой", "fixed")

    def test_history_is_kept_for_audit(self):
        self.store.record(attack())
        self.store.set_status("run:bac:1", "reported", note="передали команде агента")
        self.store.set_status("run:bac:1", "fixed")
        history = self.store.status_history("run:bac:1")
        self.assertEqual([row["status"] for row in history],
                         ["confirmed", "reported", "fixed"])
        self.assertEqual(history[1]["note"], "передали команде агента")

    def test_reopening_is_a_normal_transition(self):
        self.store.record(attack())
        self.store.set_status("run:bac:1", "closed")
        self.store.set_status("run:bac:1", "reopened")
        self.assertEqual(self.store.all_for("stand")[0]["status"], "reopened")

    def test_rerecording_a_run_does_not_reset_the_status(self):
        """Реиндексация runs/ идемпотентна и не должна терять судьбу находки."""
        self.store.record(attack())
        self.store.set_status("run:bac:1", "fixed")
        self.store.record(attack())
        self.assertEqual(self.store.all_for("stand")[0]["status"], "fixed")

    def test_lifecycle_covers_the_spec_states(self):
        self.assertEqual(
            STATUSES,
            ("open", "confirmed", "reported", "fixed", "retested", "closed", "reopened"))

    def test_existing_database_without_the_column_is_migrated(self):
        """База, наполненная до US-36, открывается и получает статус."""
        import sqlite3

        from agentic_redteam.knowledge.store import ATTACK_FIELDS
        path = Path(tempfile.mkdtemp()) / "old.sqlite"
        legacy = sqlite3.connect(path)
        # Схема до US-36: те же поля, но без status.
        legacy.execute(
            f"CREATE TABLE attacks (id TEXT PRIMARY KEY, "
            f"{', '.join(f'{f} TEXT' for f in ATTACK_FIELDS if f != 'id')})")
        legacy.execute("INSERT INTO attacks (id, profile_name) VALUES ('old:1', 'stand')")
        legacy.commit()
        legacy.close()
        store = KnowledgeStore(path)
        self.addCleanup(store.close)
        self.assertEqual(store.all_for("stand")[0]["status"], "confirmed")


class StatusCliTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "kb.sqlite"
        store = KnowledgeStore(self.path)
        store.record(attack())
        store.close()

    def run_cli(self, *argv):
        output = io.StringIO()
        with unittest.mock.patch("agentic_redteam.app_cli.KB_PATH", self.path), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(item) for item in argv])
        return code, output.getvalue()

    def test_status_command_moves_the_finding(self):
        code, out = self.run_cli("kb", "status", "run:bac:1", "--set", "fixed", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["attack"]["status"], "fixed")

    def test_status_command_shows_history(self):
        self.run_cli("kb", "status", "run:bac:1", "--set", "reported")
        code, out = self.run_cli("kb", "status", "run:bac:1", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual([row["status"] for row in json.loads(out)["history"]],
                         ["confirmed", "reported"])

    def test_unknown_status_is_a_usage_error(self):
        """Недопустимый статус отсекается разбором аргументов, как любой флаг."""
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("kb", "status", "run:bac:1", "--set", "нет", "--json")
        self.assertEqual(caught.exception.code, 2)

    def test_unknown_attack_is_a_usage_error(self):
        code, out = self.run_cli("kb", "status", "нет:такой:1", "--json")
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])


if __name__ == "__main__":
    unittest.main()
