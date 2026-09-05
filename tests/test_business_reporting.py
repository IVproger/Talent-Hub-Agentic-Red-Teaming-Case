import unittest

from agentic_redteam.reporting.business import build_business_report
from tests.fakes import FakeLLM


FINDINGS = {
    "run_id": "r1",
    "profile": "stand@1",
    "findings": [
        {"scenario_id": "bac", "attack_class": "tool_bac", "verdict": "proven",
         "severity": "critical", "boundary": "cross_user",
         "standard_refs": ["ASI03"], "evidence_refs": ["evidence-0001.json"]},
        {"scenario_id": "leak", "attack_class": "prompt_leak", "verdict": "indirect",
         "severity": "info", "evidence_refs": ["evidence-0002.json"]},
    ],
}

BUSINESS = {
    "intended_effects": [
        {"id": "advice", "statement": "Консультация по портфелю клиента"},
    ],
    "prohibited_actions": [
        {"id": "cross-read", "statement": "Чтение данных другого клиента",
         "boundaries": ["cross_user"], "effect_ids": ["advice"]},
    ],
}


class BusinessReportTests(unittest.TestCase):
    def test_only_proven_findings_become_business_risks(self):
        report = build_business_report(FINDINGS, BUSINESS)
        self.assertIn("[critical] bac", report)
        self.assertNotIn("prompt_leak", report)
        self.assertIn("evidence-0001.json", report)

    def test_explicit_profile_mapping_is_marked_as_confirmed(self):
        report = build_business_report(FINDINGS, BUSINESS)
        self.assertIn("Чтение данных другого клиента", report)
        self.assertIn("подтверждено явной привязкой профиля", report)
        self.assertIn("Консультация по портфелю клиента", report)

    def test_missing_business_input_is_stated_without_inventing_impact(self):
        report = build_business_report(FINDINGS, {})
        self.assertIn("Бизнес-эффекты не заданы", report)
        self.assertIn("не определено командой агента", report)
        self.assertIn("Финансовый ущерб не рассчитывается", report)

    def test_optional_narrative_is_fail_open(self):
        report = build_business_report(FINDINGS, BUSINESS, FakeLLM(["кратко"]))
        self.assertIn("Краткий нарратив", report)
        self.assertIn("кратко", report)


if __name__ == "__main__":
    unittest.main()
