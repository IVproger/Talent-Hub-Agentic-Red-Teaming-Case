import unittest

from agentic_redteam.assertions.verdict import Grade, CheckOutcome, verdict


def O(passed, grade):
    return CheckOutcome(passed, grade, "")


class VerdictTests(unittest.TestCase):
    def test_error_wins(self):
        self.assertEqual(verdict([O(True, Grade.STATE), O(True, Grade.ERROR)]), "error")

    def test_unobservable_not_proven(self):
        self.assertEqual(verdict([O(True, Grade.UNOBSERVABLE)]), "not_proven")

    def test_failed_assertion_not_proven(self):
        self.assertEqual(verdict([O(False, Grade.STATE)]), "not_proven")

    def test_text_only_indirect(self):
        self.assertEqual(verdict([O(True, Grade.TEXT)]), "indirect")

    def test_all_state_proven(self):
        self.assertEqual(verdict([O(True, Grade.STATE), O(True, Grade.STATE)]), "proven")

    def test_empty_not_proven(self):
        self.assertEqual(verdict([]), "not_proven")


if __name__ == "__main__":
    unittest.main()
