"""runs/<id>/ carries what a repeat needs: campaign.json and transcript.jsonl."""
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


CHAIN = [
    ScenarioStep("inject", "attacker", payload=True),
    ScenarioStep("activate", "victim", message="портфель?"),
]


def scenario(id_="chain"):
    return PlannedScenario(id=id_, attack_class="cls", standard_refs=["AML.T0012"],
                           actor="1001", payloads=["p1", "p2"],
                           goal=[{"type": "tool_principal_mismatch", "at": "activate"}],
                           boundary="user", steps=list(CHAIN))


class CampaignArtifactTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        adapter = FakeAdapter({"attacker": "1001", "victim": "1002"}, ["ok"] * 8)
        evidence = FakeEvidenceSource([
            Facts(), Facts(tool_calls=[ObservedToolCall("get_portfolio", "1003", {}, "r")]),
            Facts(), Facts(tool_calls=[ObservedToolCall("get_portfolio", "1002", {}, "r")]),
        ])
        self.findings = run_campaign([scenario()], RunnerDeps(adapter, evidence),
                                     storage=RunStorage(self.root), run_id="run1",
                                     modes=["vulnerable"], profile_ref="stand@1.0.0")
        self.run_dir = self.root / "run1"

    def test_campaign_json_records_what_was_run(self):
        campaign = json.loads((self.run_dir / "campaign.json").read_text(encoding="utf-8"))
        self.assertEqual(campaign["profile"], "stand@1.0.0")
        self.assertEqual(campaign["run_id"], "run1")
        self.assertEqual(campaign["modes"], ["vulnerable"])
        self.assertEqual(campaign["scenarios"][0]["id"], "chain")
        self.assertEqual(campaign["scenarios"][0]["payloads"], ["p1", "p2"])
        self.assertEqual([s["name"] for s in campaign["scenarios"][0]["steps"]],
                         ["inject", "activate"])

    def test_transcript_has_one_row_per_attempt(self):
        rows = [json.loads(line) for line in
                (self.run_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)                       # two payloads, one mode
        self.assertEqual([r["payload"] for r in rows], ["p1", "p2"])
        self.assertEqual([r["scenario_id"] for r in rows], ["chain", "chain"])
        self.assertEqual([r["verdict"] for r in rows], ["proven", "not_proven"])
        self.assertEqual(rows[0]["mode"], "vulnerable")
        self.assertEqual(rows[0]["outcomes"][0]["grade"], "state")
        self.assertTrue(rows[0]["outcomes"][0]["passed"])

    def test_findings_link_the_exact_attempt_evidence(self):
        rows = [json.loads(line) for line in
                (self.run_dir / "transcript.jsonl").read_text().splitlines()]
        first, second = (self.run_dir / row["evidence_refs"][0] for row in rows)
        self.assertNotEqual(first, second)
        evidence = json.loads(first.read_text())
        self.assertEqual(evidence["facts"]["tool_calls"][0]["raw"], "r")
        self.assertEqual(evidence["facts"]["tool_calls"][0]["principal"], "1003")
        self.assertEqual(evidence["mode"], "vulnerable")
        self.assertEqual(evidence["attempt"], 1)
        self.assertEqual([s["principal"] for s in evidence["steps"]], ["1001", "1002"])
        self.assertEqual(evidence["steps"][0]["facts"]["tool_calls"], [])
        self.assertEqual(evidence["steps"][1]["facts"]["tool_calls"][0]["principal"], "1003")
        self.assertEqual(rows[0]["steps"][1]["role"], "victim")
        self.assertEqual(json.loads(second.read_text())["facts"]["tool_calls"][0]["principal"], "1002")
        refs = self.findings["findings"][0]["evidence_refs"]
        self.assertEqual(refs, rows[0]["evidence_refs"])
        finding = self.findings["findings"][0]
        self.assertEqual(finding["attempt"], 1)
        self.assertEqual(finding["payload"], "p1")
        self.assertEqual([step["name"] for step in finding["chain"]], ["inject", "activate"])
        self.assertEqual(finding["chain"][1]["tool_calls"][0]["principal"], "1003")
        report = (self.run_dir / "report.md").read_text()
        self.assertIn(refs[0], report)
        self.assertIn("p1", report)
        self.assertIn("tool `get_portfolio`", report)

    def test_transcript_records_the_error_that_ended_an_attempt(self):
        root = Path(tempfile.mkdtemp())

        class Broken(FakeEvidenceSource):
            def collect_facts(self, since):
                raise RuntimeError("источник упал")

        run_campaign([scenario("s")], RunnerDeps(FakeAdapter({"attacker": "1001",
                                                             "victim": "1002"}, ["ok"] * 8),
                                                 Broken([])),
                     storage=RunStorage(root), run_id="run2")
        rows = [json.loads(line) for line in
                (root / "run2" / "transcript.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["verdict"], "error")
        self.assertIn("источник упал", rows[0]["error"])
        self.assertEqual(rows[0]["evidence_refs"], [])

    def test_provider_observations_are_frozen_before_the_next_attempt(self):
        from agentic_redteam.evidence.base import EvidenceKind, Observation

        class Source(FakeEvidenceSource):
            last_observations = {}

            def collect_facts(self, since):
                facts = super().collect_facts(since)
                self.last_observations["calls"] = [Observation(
                    EvidenceKind.TOOL_CALLS, {"principal": str(self._collected)},
                    f"raw-{self._collected}")]
                return facts

        with tempfile.TemporaryDirectory() as root:
            source = Source([Facts(), Facts(), Facts(), Facts()])
            run_campaign([scenario()], RunnerDeps(FakeAdapter(
                {"attacker": "1001", "victim": "1002"}, ["ok"] * 8), source),
                RunStorage(root), "frozen")
            first = json.loads((Path(root) / "frozen/evidence-0001.json").read_text())
            second = json.loads((Path(root) / "frozen/evidence-0002.json").read_text())
            self.assertEqual(first["observations"]["calls"][0]["raw"], "raw-1")
            self.assertEqual(second["observations"]["calls"][0]["raw"], "raw-3")


if __name__ == "__main__":
    unittest.main()
