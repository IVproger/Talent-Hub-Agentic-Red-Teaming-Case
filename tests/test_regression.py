"""E8: сравнение двух прогонов — что закрылось, осталось, появилось (US-29)."""
from __future__ import annotations

import unittest

from agentic_redteam.reporting.regression import RegressionDiff, compare


def findings(*, asr=0.0, confirmed=(), smoke=()):
    return {
        "asr_percent": asr,
        "findings": [{"scenario_id": sid, "verdict": verdict} for sid, verdict in confirmed],
        "smoke": [{"scenario_id": sid, "ok": ok, "verdict": "proven" if ok else "not_proven"}
                  for sid, ok in smoke],
    }


class CompareTests(unittest.TestCase):
    def test_attack_gone_after_fix_is_closed(self):
        before = findings(asr=100.0, confirmed=[("bac", "proven")])
        after = findings(asr=0.0, confirmed=[])
        self.assertEqual(compare(before, after).per_attack, {"bac": "closed"})

    def test_attack_still_confirmed_is_remained(self):
        before = findings(confirmed=[("bac", "proven")])
        after = findings(confirmed=[("bac", "proven")])
        self.assertEqual(compare(before, after).per_attack, {"bac": "remained"})

    def test_indirect_after_proven_still_counts_as_remained(self):
        """Понижение градации — не закрытие: атака всё ещё подтверждена."""
        before = findings(confirmed=[("bac", "proven")])
        after = findings(confirmed=[("bac", "indirect")])
        self.assertEqual(compare(before, after).per_attack, {"bac": "remained"})

    def test_new_attack_is_appeared(self):
        before = findings(confirmed=[])
        after = findings(confirmed=[("poison", "proven")])
        self.assertEqual(compare(before, after).per_attack, {"poison": "appeared"})

    def test_carries_asr_of_both_runs(self):
        diff = compare(findings(asr=75.0), findings(asr=25.0))
        self.assertEqual((diff.asr_before, diff.asr_after), (75.0, 25.0))

    def test_smoke_failure_after_fix_breaks_the_product(self):
        """US-29 AC3: закрыть дыру, сломав агента, — не успех."""
        after = findings(confirmed=[], smoke=[("normal-portfolio", False)])
        self.assertFalse(compare(findings(), after).smoke_ok)

    def test_smoke_passing_is_ok(self):
        after = findings(smoke=[("normal-portfolio", True)])
        self.assertTrue(compare(findings(), after).smoke_ok)

    def test_mixed_verdicts_are_reported_per_attack(self):
        before = findings(asr=100.0, confirmed=[("bac", "proven"), ("poison", "proven")])
        after = findings(asr=50.0, confirmed=[("poison", "proven"), ("leak", "indirect")])
        self.assertEqual(
            compare(before, after).per_attack,
            {"bac": "closed", "poison": "remained", "leak": "appeared"},
        )

    def test_diff_is_a_dataclass_with_the_spec_fields(self):
        diff = compare(findings(), findings())
        self.assertIsInstance(diff, RegressionDiff)
        self.assertEqual(diff.per_attack, {})
        self.assertTrue(diff.smoke_ok)


if __name__ == "__main__":
    unittest.main()
