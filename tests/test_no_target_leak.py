import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBID = re.compile(r"\bcus\b|mongo|invest-server|8600|agent_policy_memories", re.I)


class TargetLeakTests(unittest.TestCase):
    def test_no_target_specifics_in_core(self):
        for d in ("normalize", "assertions", "campaign"):
            for p in (ROOT / "agentic_redteam" / d).rglob("*.py"):
                m = FORBID.search(p.read_text(encoding="utf-8"))
                self.assertIsNone(m, f"target-leak in {p}: {m.group(0) if m else ''}")


if __name__ == "__main__":
    unittest.main()
