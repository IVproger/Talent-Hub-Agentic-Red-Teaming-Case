import unittest
from agentic_redteam.generation.template import Template
from agentic_redteam.generation.coverage import coverage, CoverageReport
from agentic_redteam.profile.schema import TargetProfile

STAND = TargetProfile.load("tests/data/profile_stand.yaml")


def tmpl(id_, boundary, success, requires_evidence=("tool_calls",)):
    return Template(id=id_, standard={"asi": id_.upper()}, title=id_, boundary=boundary,
                    delivery=["user_message"], requires_features=[],
                    requires_evidence=list(requires_evidence), enhanced_by=[],
                    steps=[{"role": "attacker", "act": "inject", "payload": True}],
                    success=list(success), remediation="")


class CoverageTests(unittest.TestCase):
    def test_composed_excluded_and_ceiling(self):
        report = coverage([
            tmpl("asi03", "user", [{"assert": "tool_principal_mismatch", "at": "inject"}]),
            tmpl("asi07", "agent", [{"assert": "tool_principal_mismatch", "at": "inject"}]),
            tmpl("asi01", None, [{"assert": "response_contains", "value": "x"}]),
            tmpl("asi04", "user", [{"assert": "external_callback", "token": "t"}],
                 requires_evidence=["external_callback"]),
        ], STAND)
        self.assertIsInstance(report, CoverageReport)
        by_id = {row.template_id: row for row in report.rows}
        self.assertEqual(by_id["asi03"].status, "composed")
        self.assertEqual(by_id["asi03"].ceiling, "proven")
        self.assertEqual(by_id["asi07"].status, "not_applicable")   # нет границы agent
        self.assertEqual(by_id["asi01"].status, "composed")
        self.assertEqual(by_id["asi01"].ceiling, "indirect")        # только текст
        self.assertEqual(by_id["asi04"].status, "unsupported")      # нет external_callback
        self.assertEqual(sorted(report.composed()), ["asi01", "asi03"])
        self.assertEqual({r.template_id for r in report.excluded()}, {"asi04", "asi07"})
