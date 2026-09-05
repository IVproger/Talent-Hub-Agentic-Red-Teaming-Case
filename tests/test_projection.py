import unittest

from agentic_redteam.normalize.projection import dotted, project_memory, principal_of


class ProjectionTests(unittest.TestCase):
    def test_dotted_nested(self):
        self.assertEqual(dotted({"a": {"b": "x"}}, "a.b"), "x")

    def test_dotted_list_suffix(self):
        self.assertEqual(dotted({"memories": [1, 2]}, "memories[]"), [1, 2])

    def test_scope_from_record_map(self):
        w = project_memory(
            {"fact_id": "1", "fact": "t", "scope": "global"},
            {"key": "fact_id", "content": "fact",
             "scope": {"field": "scope", "map": {"global": "cross_user"}}},
            None,
        )
        self.assertEqual((w.key, w.content, w.scope), ("1", "t", "cross_user"))

    def test_store_scope_used_when_declared(self):
        w = project_memory(
            {"_id": "9", "statement": "s"},
            {"key": "_id", "content": "statement"},
            "cross_user",
        )
        self.assertEqual(w.scope, "cross_user")

    def test_principal_argument(self):
        self.assertEqual(principal_of({"cus": "1002"}, {"kind": "argument", "name": "cus"}, None), "1002")

    def test_principal_none(self):
        self.assertIsNone(principal_of({"cus": "1002"}, {"kind": "none"}, None))

    def test_principal_call_context(self):
        self.assertEqual(principal_of({}, {"kind": "call_context", "field": "sub"}, {"sub": "1002"}), "1002")


if __name__ == "__main__":
    unittest.main()
