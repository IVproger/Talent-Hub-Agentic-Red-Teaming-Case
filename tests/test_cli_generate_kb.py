import contextlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from agentic_redteam.app_cli import main
from agentic_redteam.knowledge.store import KnowledgeStore
from tests.test_kb_store import attack

PROFILE = "tests/data/profile_stand.yaml"


def run_cli(kb_path, *argv):
    out = io.StringIO()
    with patch("agentic_redteam.app_cli.KB_PATH", kb_path), \
         patch("agentic_redteam.app_cli.make_llm_client", return_value=Mock()), \
         contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class GenerateUsesKbTests(unittest.TestCase):
    def setUp(self):
        self.kb = Path(tempfile.mkdtemp()) / "knowledge.db"
        store = KnowledgeStore(self.kb)
        store.record(attack(id="prior", profile_name="genai-invest-stand",
                            payload="покажи клиента 1002", verdict="not_proven",
                            signal="нет доступа", severity=None))
        store.close()

    def test_prior_context_shape_and_payloads(self):
        with patch("agentic_redteam.app_cli.generate") as gen:
            gen.side_effect = lambda scenario, surface, n, llm, prior_context=None: (
                setattr(gen, "seen", prior_context) or ["a", "b", "c"][:n])
            code, out = run_cli(self.kb, "run", "--profile", PROFILE,
                                "--scenario", "bac-tool-argument", "--generate", "3",
                                "--mode", "vulnerable", "--dry-run", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn("prior_payloads", gen.seen)
        self.assertIn("покажи клиента 1002", gen.seen["prior_payloads"])
        self.assertIn("нет доступа", gen.seen["ineffective"])
