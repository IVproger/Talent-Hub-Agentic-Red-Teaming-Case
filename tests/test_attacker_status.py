import unittest

from agentic_redteam.attacker.status import (
    attempt_outcome_label,
    classify_unscored,
)


class AttackerStatusTests(unittest.TestCase):
    def test_scored_budget_exhaustion_keeps_judge_verdict(self):
        self.assertEqual(attempt_outcome_label({
            "status": "scored", "judge_verdict": "NO",
            "stop_reason": "max_turns",
        }), "NO")
        self.assertEqual(attempt_outcome_label({
            "status": "scored", "judge_verdict": "YES",
            "stop_reason": "deadline",
        }), "YES")

    def test_attacker_decision_timeout_is_presented_as_unscored(self):
        row = {
            "status": "error", "judge_verdict": None,
            "stop_reason": "turn_timeout",
            "error": "Решение атакующего не уложилось в turn_timeout (40s)",
        }
        self.assertEqual(
            attempt_outcome_label(row),
            "НЕ ОЦЕНЕНО · таймаут решения атакующего",
        )

    def test_unscored_stage_is_classified_for_persisted_results(self):
        self.assertEqual(
            classify_unscored("submit_attack", None, "judge unavailable"),
            "judge_failure",
        )
        self.assertEqual(
            classify_unscored(None, "TargetUnavailable", None),
            "attempt_failure",
        )
        self.assertEqual(
            classify_unscored("llm_failure", "bad action", None),
            "attacker_invalid_action",
        )


if __name__ == "__main__":
    unittest.main()
