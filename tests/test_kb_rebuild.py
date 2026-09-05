import json, tempfile, unittest
from pathlib import Path
from agentic_redteam.knowledge.store import KnowledgeStore
from tests.test_kb_ingest import make_run


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.runs = Path(tempfile.mkdtemp())
        make_run(self.runs)
        (self.runs / "broken").mkdir()
        self.store = KnowledgeStore(Path(tempfile.mkdtemp()) / "knowledge.db")

    def test_record_run_counts_attempts(self):
        run = next(p for p in self.runs.iterdir() if (p / "campaign.json").is_file())
        self.assertEqual(self.store.record_run(run), 2)

    def test_rebuild_indexes_all_valid_runs(self):
        self.assertEqual(self.store.rebuild_from_runs(self.runs), 2)
        self.assertEqual(len(self.store.all_for("genai-invest-stand")), 2)

    def test_rebuild_is_idempotent(self):
        self.store.rebuild_from_runs(self.runs)
        self.store.rebuild_from_runs(self.runs)
        self.assertEqual(len(self.store.all_for("genai-invest-stand")), 2)


class RebuildReplacesTests(unittest.TestCase):
    """«Переналить из runs/» означает заменить, а не дописать поверх."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.runs = self.root / "runs"
        self.runs.mkdir()
        self.store = KnowledgeStore(self.root / "kb.sqlite")
        self.addCleanup(self.store.close)

    def test_rows_whose_run_is_gone_are_dropped(self):
        self.store.record({"id": "old:x:1", "campaign_run_id": "old",
                           "profile_name": "p", "scenario_id": "x", "payload": "устарело"})
        self.assertEqual(len(self.store.all_for("p")), 1)
        self.store.rebuild_from_runs(self.runs)
        self.assertEqual(self.store.all_for("p"), [],
                         "запись без прогона в runs/ должна уйти")

    def test_status_survives_the_rebuild(self):
        """US-36: судьба находки не должна теряться при реиндексации."""
        make_run(self.runs)
        self.store.rebuild_from_runs(self.runs)
        attack_id = self.store.all_for("genai-invest-stand")[0]["id"]
        self.store.set_status(attack_id, "fixed", note="починили")
        self.store.rebuild_from_runs(self.runs)
        self.assertEqual(self.store.get(attack_id)["status"], "fixed")
        self.assertIn("починили",
                      [h["note"] for h in self.store.status_history(attack_id)])

    def test_row_the_ingest_no_longer_produces_is_dropped(self):
        """Прогон на месте, но запись устарела (например, штатный сценарий).

        «Переналить» — значит привести базу к тому, что даёт ingest сейчас,
        а не только выкинуть записи исчезнувших прогонов.
        """
        run = make_run(self.runs)
        self.store.rebuild_from_runs(self.runs)
        self.store.record({"id": f"{run.name}:stale:9", "campaign_run_id": run.name,
                           "profile_name": "genai-invest-stand", "scenario_id": "stale",
                           "payload": "уже не производится"})
        self.assertIn("stale", [a["scenario_id"] for a in self.store.all_for("genai-invest-stand")])
        self.store.rebuild_from_runs(self.runs)
        self.assertNotIn("stale",
                         [a["scenario_id"] for a in self.store.all_for("genai-invest-stand")])
