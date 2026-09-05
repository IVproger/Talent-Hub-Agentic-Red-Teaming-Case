"""build_findings: chain stage, multi-scenario campaigns, stated limitations."""
from __future__ import annotations

import unittest

from agentic_redteam.assertions.verdict import CheckOutcome, Grade
from agentic_redteam.campaign.orchestrator import PlannedScenario, build_findings
from agentic_redteam.campaign.runner import AttemptResult, RunResult, ScenarioStep
from agentic_redteam.reporting.technical import build_skeleton


CHAIN = [
    ScenarioStep("inject", "attacker", payload=True),
    ScenarioStep("finalize", "attacker", commit_memory=True),
    ScenarioStep("activate", "victim", message="портфель?"),
]


def scenario(id_, goal, steps=(), boundary="user", actor="1001"):
    return PlannedScenario(id=id_, attack_class="cls", standard_refs=["AML.T0012"],
                           actor=actor, payloads=["p"], goal=goal,
                           boundary=boundary, steps=list(steps))


def attempts(*specs):
    rows = []
    for index, (verdict_, outcomes, mode) in enumerate(specs, start=1):
        rows.append(AttemptResult(index, "p", "1001", mode, verdict_, list(outcomes)))
    return RunResult("r", "completed", rows, 0.0, None)


def ok(grade=Grade.STATE, detail="сработало"):
    return CheckOutcome(True, grade, detail)


def no(grade=Grade.STATE, detail="не сработало"):
    return CheckOutcome(False, grade, detail)


class ChainStageTests(unittest.TestCase):
    def _stage(self, goal, outcomes, steps=CHAIN):
        results = [(scenario("s", goal, steps), attempts(("proven", outcomes, "vulnerable")))]
        return build_findings("r1", "p@1", ["vulnerable"], results)["findings"][0]["chain_stage"]

    def test_tool_call_is_the_action_stage(self):
        self.assertEqual(
            self._stage([{"type": "tool_principal_mismatch", "at": "activate"}], [ok()]),
            "действие")

    def test_memory_write_is_the_persistence_stage(self):
        self.assertEqual(
            self._stage([{"type": "memory_write", "scope": "cross_user"}], [ok()]),
            "закрепление")

    def test_stage_follows_the_predicate_that_fired(self):
        goal = [{"type": "memory_write", "scope": "cross_user"},
                {"type": "tool_principal_mismatch", "at": "activate"}]
        self.assertEqual(self._stage(goal, [no(), ok()]), "действие")
        self.assertEqual(self._stage(goal, [ok(), no()]), "закрепление")

    def test_text_only_evidence_is_not_promoted_to_a_finding(self):
        results = [(scenario("leak", [{"type": "response_contains", "value": "x"}], []),
                    attempts(("indirect", [ok(Grade.TEXT)], "vulnerable")))]
        built = build_findings("r1", "p@1", [], results)
        self.assertEqual(built["findings"], [])
        self.assertTrue(any("indirect" in note for note in built["limitations"]))


class MultiScenarioTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            (scenario("chain", [{"type": "tool_principal_mismatch", "at": "activate"}], CHAIN),
             attempts(("not_proven", [no()], "vulnerable"), ("proven", [ok()], "protected"))),
            (scenario("leak", [{"type": "response_contains", "value": "x"}], [], boundary=None,
                      actor="1002"),
             attempts(("indirect", [ok(Grade.TEXT)], "vulnerable"))),
        ]
        self.findings = build_findings("r1", "stand@1.0.0", ["vulnerable", "protected"],
                                       self.results)

    def test_only_state_proven_scenarios_get_findings(self):
        self.assertEqual([f["scenario_id"] for f in self.findings["findings"]], ["chain"])

    def test_finding_carries_the_facts_needed_to_repeat_it(self):
        chain = self.findings["findings"][0]
        self.assertEqual(chain["mode"], "protected")     # the attempt that proved it
        self.assertEqual(chain["roles"], "1001")
        self.assertEqual(chain["reset_policy"], "per_scenario")
        self.assertEqual((chain["attempts_proven"], chain["attempts_total"]), (1, 2))

    def test_reproduction_covers_the_whole_campaign(self):
        reproduction = self.findings["reproduction"]
        self.assertEqual(reproduction["scenario"], "chain, leak")
        self.assertEqual(reproduction["roles"], "1001, 1002")
        self.assertEqual(reproduction["mode"], "vulnerable, protected")
        self.assertEqual(reproduction["profile"], "stand@1.0.0")

    def test_report_keeps_indirect_in_attempts_not_findings(self):
        markdown = build_skeleton(self.findings)
        self.assertIn("chain", markdown)
        self.assertIn("leak", markdown)
        self.assertIn("действие", markdown)
        self.assertNotIn("### [info] leak", markdown)


class LimitationsTests(unittest.TestCase):
    def _limitations(self, results):
        return build_findings("r1", "p@1", [], results)["limitations"]

    def test_text_only_verdict_is_declared(self):
        results = [(scenario("leak", [{"type": "response_contains", "value": "x"}], []),
                    attempts(("indirect", [ok(Grade.TEXT)], None)))]
        self.assertTrue(any("indirect" in note for note in self._limitations(results)))

    def test_unobservable_check_is_declared(self):
        results = [(scenario("s", [{"type": "tool_principal_mismatch"}], []),
                    attempts(("not_proven",
                              [CheckOutcome(False, Grade.UNOBSERVABLE, "нет источника вызовов")],
                              None)))]
        self.assertTrue(any("нет источника вызовов" in note for note in self._limitations(results)))

    def test_errors_are_declared_as_outside_asr(self):
        results = [(scenario("s", [{"type": "tool_principal_mismatch"}], []),
                    attempts(("error", [], None)))]
        self.assertTrue(any("ASR" in note for note in self._limitations(results)))

    def test_clean_campaign_states_no_limitations(self):
        results = [(scenario("s", [{"type": "tool_principal_mismatch"}], []),
                    attempts(("proven", [ok()], None)))]
        self.assertEqual(self._limitations(results), [])


if __name__ == "__main__":
    unittest.main()
