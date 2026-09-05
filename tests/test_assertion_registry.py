import unittest
from agentic_redteam.assertions.registry import required_kinds, REQUIRED


class RegistryTests(unittest.TestCase):
    def test_required_union(self):
        goal = [{"type": "memory_write", "scope": "cross_user"},
                {"type": "tool_principal_mismatch", "at": "activate"}]
        self.assertEqual(required_kinds(goal), {"memory_snapshot", "tool_calls"})

    def test_text_predicate_needs_nothing(self):
        self.assertEqual(required_kinds([{"type": "response_contains", "value": "x"}]), set())

    def test_all_types_registered(self):
        for t in ("tool_principal_mismatch", "memory_write", "external_callback",
                  "isolation_violation", "cross_session_effect", "response_contains"):
            self.assertIn(t, REQUIRED)


if __name__ == "__main__":
    unittest.main()
