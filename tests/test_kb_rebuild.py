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
