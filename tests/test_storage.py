from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_redteam.run_storage import RunStorage, StorageError


class StorageTests(unittest.TestCase):
    def test_runs_are_distinct_and_path_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = RunStorage(temp)
            first = storage.create("one")
            second = storage.create("two")
            self.assertNotEqual(first, second)
            with self.assertRaises(StorageError):
                storage.create("../escape")
            with self.assertRaises(StorageError):
                storage.create("one")

    def test_invalid_history_is_listable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "broken").mkdir()
            rows = RunStorage(root).list_runs()
            self.assertEqual(rows[0]["status"], "invalid")

    def test_non_object_status_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "broken"
            run.mkdir()
            (run / "status.json").write_text("[]", encoding="utf-8")
            rows = RunStorage(root).list_runs()
            self.assertEqual(rows[0]["status"], "invalid")

    def test_inconsistent_run_id_and_unknown_status_are_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, payload in (
                ("wrong-id", '{"run_id":"different","status":"completed"}'),
                ("wrong-status", '{"run_id":"wrong-status","status":"garbage"}'),
            ):
                run = root / name
                run.mkdir()
                (run / "status.json").write_text(payload, encoding="utf-8")
            rows = RunStorage(root).list_runs()
            self.assertEqual({item["status"] for item in rows}, {"invalid"})


if __name__ == "__main__":
    unittest.main()
