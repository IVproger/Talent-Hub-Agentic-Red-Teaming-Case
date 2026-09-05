"""US-36: replay results advance fixed findings without overriding humans."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_redteam.knowledge.lifecycle import advance_retests
from agentic_redteam.knowledge.store import KnowledgeStore


def attack(attack_id: str, scenario_id: str, *, verdict: str = "proven") -> dict:
    return {
        "id": attack_id,
        "campaign_run_id": "source",
        "profile_name": "stand",
        "profile_version": "1.0.0",
        "scenario_id": scenario_id,
        "attack_class": "bac",
        "payload": "payload",
        "mode": "vulnerable",
        "verdict": verdict,
    }


def result(*, proven=()) -> dict:
    scenarios = ["bac", "poison"]
    return {
        "run_id": "retest",
        "attempts": [
            {
                "scenario_id": scenario,
                "mode": "vulnerable",
                "verdict": "proven" if scenario in proven else "not_proven",
            }
            for scenario in scenarios
        ],
        "findings": [
            {"scenario_id": scenario, "mode": "vulnerable", "verdict": "proven"}
            for scenario in proven
        ],
    }


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.store = KnowledgeStore(Path(tempfile.mkdtemp()) / "kb.sqlite")
        self.addCleanup(self.store.close)
        self.store.record(attack("source:bac:1", "bac"))
        self.store.record(attack("source:poison:1", "poison"))

    def test_fixed_finding_closes_after_clean_retest(self):
        self.store.set_status("source:bac:1", "fixed")
        updates = advance_retests(self.store, ["source"], result())
        self.assertEqual(updates[0]["status"], "closed")
        self.assertEqual(
            [item["status"] for item in self.store.status_history("source:bac:1")],
            ["confirmed", "fixed", "retested", "closed"],
        )

    def test_fixed_finding_reopens_when_attack_remains(self):
        self.store.set_status("source:bac:1", "fixed")
        updates = advance_retests(self.store, ["source"], result(proven=["bac"]))
        self.assertEqual(updates[0]["status"], "reopened")

    def test_human_owned_non_fixed_status_is_not_overwritten(self):
        self.store.set_status("source:bac:1", "reported")
        self.assertEqual(advance_retests(
            self.store, ["source"], result(proven=["bac"])
        ), [])
        self.assertEqual(self.store.get("source:bac:1")["status"], "reported")

    def test_scenario_not_executed_is_not_treated_as_closed(self):
        self.store.set_status("source:bac:1", "fixed")
        after = {"run_id": "retest", "attempts": [], "findings": []}
        self.assertEqual(advance_retests(self.store, ["source"], after), [])
        self.assertEqual(self.store.get("source:bac:1")["status"], "fixed")

    def test_non_proven_source_attempt_is_not_a_lifecycle_finding(self):
        self.store.record(attack("source:quiet:1", "bac", verdict="not_proven"))
        self.store.set_status("source:quiet:1", "fixed")
        advance_retests(self.store, ["source"], result())
        self.assertEqual(self.store.get("source:quiet:1")["status"], "fixed")

    def test_modes_are_retested_independently(self):
        self.store.record(attack("source:bac:protected", "bac") | {"mode": "protected"})
        self.store.set_status("source:bac:protected", "fixed")
        self.assertEqual(advance_retests(
            self.store, ["source"], result(proven=["bac"])
        ), [])
        self.assertEqual(self.store.get("source:bac:protected")["status"], "fixed")


if __name__ == "__main__":
    unittest.main()
