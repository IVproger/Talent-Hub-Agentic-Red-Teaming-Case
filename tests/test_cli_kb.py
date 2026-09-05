import contextlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from agentic_redteam.app_cli import main
from agentic_redteam.knowledge.store import KnowledgeStore
from tests.test_kb_store import attack


def run_cli(kb_path, *argv):
    out = io.StringIO()
    with patch("agentic_redteam.app_cli.KB_PATH", kb_path), contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class CliKbTests(unittest.TestCase):
    def setUp(self):
        self.kb = Path(tempfile.mkdtemp()) / "knowledge.db"
        store = KnowledgeStore(self.kb)
        store.record(attack(id="a", payload="утечка промпта", attack_class="LLM08"))
        store.close()

    def test_list_by_profile_json(self):
        code, out = run_cli(self.kb, "kb", "list", "--profile", "genai-invest-stand", "--json")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(len(payload["attacks"]), 1)
        self.assertEqual(payload["attacks"][0]["attack_class"], "LLM08")

    def test_search_contains(self):
        code, out = run_cli(self.kb, "kb", "search", "--contains", "утечка", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(json.loads(out)["attacks"]), 1)

    def test_rebuild_reports_count(self):
        with tempfile.TemporaryDirectory() as runs:
            from tests.test_kb_ingest import make_run
            make_run(Path(runs))
            fresh = Path(tempfile.mkdtemp()) / "kb.db"
            code, out = run_cli(fresh, "kb", "rebuild", "--runs", runs, "--json")
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)["recorded"], 2)
