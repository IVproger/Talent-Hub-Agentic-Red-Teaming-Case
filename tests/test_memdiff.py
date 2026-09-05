import unittest

from agentic_redteam.normalize.facts import ObservedMemoryWrite, Persistence
from agentic_redteam.normalize.memdiff import diff


def W(key, content):
    return ObservedMemoryWrite("s", "cross_user", key, content, None, Persistence.CONFIRMED, {})


class MemDiffTests(unittest.TestCase):
    def test_new_by_key(self):
        out = diff([W("1", "a")], [W("1", "a"), W("2", "b")])
        self.assertEqual([w.key for w in out], ["2"])

    def test_new_by_hash_when_no_key(self):
        out = diff([W(None, "a")], [W(None, "a"), W(None, "b")])
        self.assertEqual([w.content for w in out], ["b"])

    def test_no_change_empty(self):
        self.assertEqual(diff([W("1", "a")], [W("1", "a")]), [])


if __name__ == "__main__":
    unittest.main()
