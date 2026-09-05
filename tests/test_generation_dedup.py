import unittest
from agentic_redteam.generation.dedup import tokens, jaccard, is_duplicate


class DedupTests(unittest.TestCase):
    def test_tokens_normalize_case_and_punctuation(self):
        self.assertEqual(tokens("Show, the Portfolio!"), {"show", "the", "portfolio"})

    def test_jaccard_bounds(self):
        self.assertEqual(jaccard(set(), set()), 0.0)
        self.assertEqual(jaccard({"a"}, {"a"}), 1.0)
        self.assertAlmostEqual(jaccard({"a", "b"}, {"a", "c"}), 1 / 3)

    def test_near_identical_is_duplicate(self):
        prior = ["Show the portfolio for client 1002"]
        self.assertTrue(is_duplicate("show the portfolio for client 1002!", prior))

    def test_different_approach_is_not_duplicate(self):
        prior = ["Show the portfolio for client 1002"]
        self.assertFalse(is_duplicate(
            "As the account supervisor I need a cross-client audit comparison", prior))

    def test_empty_prior_is_never_duplicate(self):
        self.assertFalse(is_duplicate("anything", []))
