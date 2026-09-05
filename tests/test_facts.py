import unittest
from dataclasses import FrozenInstanceError

from agentic_redteam.normalize.facts import (
    Persistence, ObservedToolCall, ObservedMemoryWrite, ObservedCallback, Facts,
)


class FactsTests(unittest.TestCase):
    def test_tool_call_construction(self):
        c = ObservedToolCall(tool="t", principal="1002", args={"cus": "1002"}, raw="r")
        self.assertEqual(c.principal, "1002")
        self.assertEqual(c.args["cus"], "1002")

    def test_frozen(self):
        c = ObservedToolCall("t", None, {}, "r")
        with self.assertRaises(FrozenInstanceError):
            c.tool = "x"

    def test_memory_write_fields(self):
        w = ObservedMemoryWrite("s", "cross_user", "1", "poison", None, Persistence.CONFIRMED, {})
        self.assertEqual(w.persistence, Persistence.CONFIRMED)
        self.assertEqual(w.scope, "cross_user")

    def test_callback(self):
        self.assertEqual(ObservedCallback(token="T", source="canary").token, "T")

    def test_facts_empty(self):
        f = Facts()
        self.assertEqual((f.tool_calls, f.memory_writes, f.callbacks), ([], [], []))

    def test_persistence_is_str(self):
        self.assertEqual(Persistence.CONFIRMED, "confirmed")


if __name__ == "__main__":
    unittest.main()
