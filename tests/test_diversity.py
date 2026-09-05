"""US-13: покрытие и разнообразие показываются наравне с ASR.

ASR в адаптивной кампании легко «накрутить» повтором одной удачной атаки,
поэтому рядом с ним всегда идёт то, насколько широко кампания прошлась по
стандарту и по поверхности цели.
"""
from __future__ import annotations

import unittest

from agentic_redteam.assertions.verdict import CheckOutcome, Grade
from agentic_redteam.campaign.orchestrator import PlannedScenario, build_findings
from agentic_redteam.campaign.runner import AttemptResult, RunResult
from agentic_redteam.normalize.facts import Facts, ObservedMemoryWrite, ObservedToolCall
from agentic_redteam.normalize.facts import Persistence
from agentic_redteam.reporting.technical import build_skeleton


def scenario(scenario_id, attack_class="bac", refs=("ASI-01",), boundary="user"):
    return PlannedScenario(
        id=scenario_id, attack_class=attack_class, standard_refs=list(refs),
        actor="1001", payloads=["p"], boundary=boundary,
        goal=[{"type": "tool_principal_mismatch", "at": "activate"}],
    )


def attempt(payload, verdict="proven", tools=(), stores=()):
    facts = Facts(
        tool_calls=[ObservedToolCall(name, "1001", {}, "raw") for name in tools],
        memory_writes=[ObservedMemoryWrite(store, "user", None, "c", "1001",
                                           Persistence.CONFIRMED, {}) for store in stores],
    )
    return AttemptResult(1, payload, "1001", "vulnerable", verdict,
                         [CheckOutcome(verdict == "proven", Grade.STATE, "d")], facts=facts)


def findings_for(pairs):
    results = [(scen, RunResult("r", "completed", attempts, 0.0)) for scen, attempts in pairs]
    return build_findings("run", "p@1", ["vulnerable"], results)


class DiversityTests(unittest.TestCase):
    def test_standard_points_touched_are_collected(self):
        report = findings_for([
            (scenario("a", refs=["ASI-01", "LLM01"]), [attempt("x")]),
            (scenario("b", refs=["ASI-01"]), [attempt("y")]),
        ])
        self.assertEqual(report["diversity"]["standard_refs"], ["ASI-01", "LLM01"])

    def test_distinct_approaches_not_repeats(self):
        """Пять попыток одним payload'ом — один подход, а не пять."""
        report = findings_for([(scenario("a"), [attempt("same") for _ in range(5)])])
        self.assertEqual(report["diversity"]["payloads"], 1)
        self.assertEqual(report["attempts_total"], 5)

    def test_different_payloads_count_as_different_approaches(self):
        report = findings_for([(scenario("a"), [attempt("one"), attempt("two")])])
        self.assertEqual(report["diversity"]["payloads"], 2)

    def test_surface_touched_lists_tools_and_stores(self):
        report = findings_for([
            (scenario("a"), [attempt("x", tools=["get_portfolio"], stores=["mem"])]),
            (scenario("b"), [attempt("y", tools=["place_order"])]),
        ])
        self.assertEqual(report["diversity"]["tools"], ["get_portfolio", "place_order"])
        self.assertEqual(report["diversity"]["stores"], ["mem"])

    def test_boundaries_and_attack_classes_are_counted(self):
        report = findings_for([
            (scenario("a", attack_class="bac", boundary="user"), [attempt("x")]),
            (scenario("b", attack_class="poison", boundary="session"), [attempt("y")]),
        ])
        self.assertEqual(report["diversity"]["attack_classes"], ["bac", "poison"])
        self.assertEqual(report["diversity"]["boundaries"], ["session", "user"])

    def test_scenario_count_is_reported(self):
        report = findings_for([(scenario("a"), [attempt("x")]),
                               (scenario("b"), [attempt("y")])])
        self.assertEqual(report["diversity"]["scenarios"], 2)

    def test_errors_do_not_inflate_the_surface(self):
        """Ошибочная попытка ничего не доказала и поверхность не покрыла."""
        report = findings_for([(scenario("a"), [attempt("x", verdict="error", tools=["t"])])])
        self.assertEqual(report["diversity"]["tools"], [])

    def test_report_shows_coverage_next_to_asr(self):
        report = findings_for([(scenario("a", refs=["ASI-01"]),
                                [attempt("x", tools=["get_portfolio"])])])
        text = build_skeleton(report)
        self.assertIn("Покрытие и разнообразие", text)
        self.assertIn("ASI-01", text)
        self.assertIn("get_portfolio", text)


if __name__ == "__main__":
    unittest.main()
