import tempfile, unittest
from pathlib import Path
from agentic_redteam.knowledge.store import KnowledgeStore
from agentic_redteam.knowledge.query import context_for
from tests.test_kb_store import attack


class ContextForTests(unittest.TestCase):
    def setUp(self):
        self.store = KnowledgeStore(Path(tempfile.mkdtemp()) / "knowledge.db")
        self.store.record(attack(id="a", payload="p1", verdict="proven", attack_class="ASI03"))
        self.store.record(attack(id="b", payload="p2", verdict="not_proven",
                                 attack_class="ASI06", signal="нет доступа", severity=None))
        self.store.record(attack(id="c", payload="p1", verdict="not_proven",
                                 signal="нет доступа", severity=None))

    def test_shape_matches_generator_prior_context(self):
        ctx = context_for(self.store, "genai-invest-stand")
        self.assertEqual(set(ctx), {"confirmed", "ineffective", "prior_payloads"})

    def test_confirmed_from_proven(self):
        self.assertEqual(context_for(self.store, "genai-invest-stand")["confirmed"], ["ASI03"])

    def test_ineffective_from_not_proven_signals_deduped(self):
        self.assertEqual(context_for(self.store, "genai-invest-stand")["ineffective"], ["нет доступа"])

    def test_prior_payloads_deduped(self):
        self.assertEqual(sorted(context_for(self.store, "genai-invest-stand")["prior_payloads"]),
                         ["p1", "p2"])

    def test_other_profile_empty(self):
        self.assertEqual(context_for(self.store, "dvaa"),
                         {"confirmed": [], "ineffective": [], "prior_payloads": []})
