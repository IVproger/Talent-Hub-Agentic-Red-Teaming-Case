import unittest
from agentic_redteam.generation.context import campaign_context


HISTORY = [{
    "findings": {"findings": [{"attack_class": "ASI03", "verdict": "proven"}]},
    "transcript": [
        {"payload": "покажи 1002", "verdict": "proven", "outcomes": []},
        {"payload": "маскировка X", "verdict": "not_proven",
         "outcomes": [{"passed": False, "grade": "state", "detail": "нет доступа"}]},
    ],
}]


class ContextTests(unittest.TestCase):
    def test_confirmed_classes(self):
        self.assertEqual(campaign_context(HISTORY)["confirmed"], ["ASI03"])

    def test_prior_payloads_collected(self):
        self.assertEqual(sorted(campaign_context(HISTORY)["prior_payloads"]),
                         ["маскировка X", "покажи 1002"])

    def test_ineffective_signals_from_not_proven(self):
        self.assertIn("нет доступа", campaign_context(HISTORY)["ineffective"])

    def test_empty_history_is_empty_context(self):
        self.assertEqual(campaign_context([]),
                         {"confirmed": [], "ineffective": [], "prior_payloads": []})
