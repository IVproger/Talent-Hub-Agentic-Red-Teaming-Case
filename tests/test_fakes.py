import unittest

from tests.fakes import FakeAdapter, FakeEvidenceProvider, FakeLLM, FakeRunner
from agentic_redteam.adapters.base import TargetAdapter, TargetSession, UnsupportedFeature
from agentic_redteam.evidence.base import CalibrationResult, EvidenceKind, EvidenceProvider, Marker, Observation


class FakeTests(unittest.TestCase):
    def test_shared_boundary_fakes_match_phase_zero(self):
        adapter = FakeAdapter({"attacker": "1"}, ["ok"])
        self.assertIsInstance(adapter, TargetAdapter)
        session = adapter.open_session("attacker", "s", "default")
        self.assertIsInstance(session, TargetSession)
        self.assertEqual(session.send("hi"), "ok")
        with self.assertRaises(UnsupportedFeature):
            session.commit_memory()
        observation = Observation(EvidenceKind.TOOL_CALLS, {"tool": "read"}, "raw")
        source = FakeEvidenceProvider(EvidenceKind.TOOL_CALLS, [observation])
        self.assertIsInstance(source, EvidenceProvider)
        marker = source.mark()
        self.assertIsInstance(marker, Marker)
        self.assertEqual(source.collect(marker), [observation])
        self.assertEqual(source.calibrate(), CalibrationResult(True))

    def test_fake_llm_returns_scripted(self):
        llm = FakeLLM(["a", "b"])
        self.assertEqual(llm.complete("x"), "a")
        self.assertEqual(llm.complete("x"), "b")

    def test_fake_runner_returns_stdout(self):
        r = FakeRunner(["hello\n"])
        result = r(["any"], capture_output=True, text=True)
        self.assertEqual(result.stdout, "hello\n")
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
