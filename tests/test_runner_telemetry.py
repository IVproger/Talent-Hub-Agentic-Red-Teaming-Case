import unittest
from tests.fakes import FakeAdapter, FakeEvidenceSource, FakeTelemetry
from agentic_redteam.normalize.facts import Facts, ObservedToolCall
from agentic_redteam.campaign.runner import RunnerDeps, run_scenario


def facts_with(p):
    return Facts(tool_calls=[ObservedToolCall("t", p, {}, "r")])


class RunnerTelemetryTests(unittest.TestCase):
    def _deps(self, telemetry):
        return RunnerDeps(FakeAdapter({"attacker": "1001"}, ["ok"]),
                          FakeEvidenceSource([facts_with("1002")]), telemetry=telemetry)

    def test_emits_observations(self):
        t = FakeTelemetry()
        run_scenario(["p"], [{"type": "tool_principal_mismatch", "at": "a"}], "1001", self._deps(t))
        self.assertTrue(t.names)  # emitted at least one span

    def test_fail_open_when_telemetry_raises(self):
        t = FakeTelemetry(raises=True)
        res = run_scenario(["p"], [{"type": "tool_principal_mismatch", "at": "a"}], "1001", self._deps(t))
        self.assertEqual(res.attempts[0].verdict, "proven")  # verdict unaffected

    def test_no_telemetry_ok(self):
        deps = RunnerDeps(FakeAdapter({"attacker": "1001"}, ["ok"]), FakeEvidenceSource([facts_with("1002")]))
        res = run_scenario(["p"], [{"type": "tool_principal_mismatch", "at": "a"}], "1001", deps)
        self.assertEqual(res.attempts[0].verdict, "proven")


if __name__ == "__main__":
    unittest.main()
