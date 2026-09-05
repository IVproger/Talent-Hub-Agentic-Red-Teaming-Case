"""US-18: ход кампании наблюдаем, прерывание сохраняет собранное."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentic_redteam.campaign.orchestrator import PlannedScenario, run_campaign
from agentic_redteam.campaign.runner import RunnerDeps, ScenarioStep
from agentic_redteam.normalize.facts import Facts, ObservedToolCall
from agentic_redteam.storage.runs import RunStorage
from tests.fakes import FakeAdapter, FakeEvidenceSource


def hit(principal="1002"):
    return Facts(tool_calls=[ObservedToolCall("get_portfolio", principal, {}, "raw")])


def scenario(id_="bac", payloads=("p1", "p2")):
    return PlannedScenario(id=id_, attack_class="cls", standard_refs=["AML.T0012"],
                           actor="1001", payloads=list(payloads),
                           goal=[{"type": "tool_principal_mismatch"}],
                           boundary="user",
                           steps=[ScenarioStep("activate", "attacker", payload=True)])


def deps(facts_count=16):
    return RunnerDeps(FakeAdapter({"attacker": "1001", "victim": "1002"}, ["ok"] * 40),
                      FakeEvidenceSource([hit()] * facts_count))


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.events = []

    def _run(self, scenarios, modes=None, trials=1, run_id="r1"):
        return run_campaign(scenarios, deps(), storage=RunStorage(self.root), run_id=run_id,
                            modes=modes, trials=trials, on_event=self.events.append)

    def test_every_attempt_reports_progress(self):
        self._run([scenario()], modes=["vulnerable"])
        attempts = [e for e in self.events if e.stage == "attempt"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual([e.attempt for e in attempts], [1, 2])
        self.assertTrue(all(e.total == 2 for e in attempts))
        self.assertEqual(attempts[0].data["verdict"], "proven")

    def test_attempt_numbering_spans_the_whole_campaign(self):
        self._run([scenario("a"), scenario("b")], modes=["vulnerable"])
        attempts = [e for e in self.events if e.stage == "attempt"]
        self.assertEqual([e.attempt for e in attempts], [1, 2, 3, 4])
        self.assertTrue(all(e.total == 4 for e in attempts))
        self.assertEqual([e.data["scenario_id"] for e in attempts], ["a", "a", "b", "b"])

    def test_total_accounts_for_modes_and_trials(self):
        self._run([scenario()], modes=["vulnerable", "protected"], trials=2)
        self.assertTrue(all(e.total == 8 for e in self.events if e.stage == "attempt"))

    def test_campaign_announces_scenarios_and_completion(self):
        self._run([scenario("a")], modes=["vulnerable"])
        stages = [e.stage for e in self.events]
        self.assertEqual(stages[0], "scenario")
        self.assertEqual(stages[-1], "completed")
        self.assertIn("report", stages)
        self.assertEqual(self.events[0].data["scenario_id"], "a")

    def test_a_broken_listener_never_breaks_the_run(self):
        def explode(_event):
            raise RuntimeError("UI упал")

        findings = run_campaign([scenario()], deps(), storage=RunStorage(self.root),
                                run_id="r2", modes=["vulnerable"], on_event=explode)
        self.assertEqual(findings["asr_percent"], 100.0)


class InterruptTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_interrupt_saves_what_was_collected_and_propagates(self):
        def stop_on_second(event):
            if event.stage == "scenario" and event.data["scenario_id"] == "b":
                raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_campaign([scenario("a"), scenario("b")], deps(),
                         storage=RunStorage(self.root), run_id="r3",
                         modes=["vulnerable"], on_event=stop_on_second)
        run_dir = self.root / "r3"
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "interrupted")
        findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
        self.assertEqual([f["scenario_id"] for f in findings["findings"]], ["a"])
        self.assertIn("еполн", (run_dir / "report.md").read_text(encoding="utf-8"))
        rows = (run_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 2)      # то, что успело пройти, сохранено


if __name__ == "__main__":
    unittest.main()
