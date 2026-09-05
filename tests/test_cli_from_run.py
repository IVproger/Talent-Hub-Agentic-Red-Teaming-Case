"""run --from runs/<id>: сохранённая кампания достаточна, чтобы её повторить."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agentic_redteam.app_cli import main
from agentic_redteam.campaign.orchestrator import PlannedScenario, run_campaign
from agentic_redteam.campaign.runner import RunnerDeps, ScenarioStep
from agentic_redteam.normalize.facts import Facts, ObservedToolCall
from agentic_redteam.storage.runs import RunStorage
from tests.fakes import FakeAdapter, FakeEvidenceSource


def run_cli(*argv) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(list(argv))
    return code, output.getvalue()


def saved_run(root: Path, trials: int = 1) -> Path:
    scenario = PlannedScenario(
        id="chain", attack_class="cls", standard_refs=["AML.T0012"], actor="1001",
        payloads=["отрава"], goal=[{"type": "tool_principal_mismatch", "at": "activate"}],
        boundary="user",
        steps=[ScenarioStep("inject", "attacker", payload=True),
               ScenarioStep("activate", "victim", message="портфель?")],
    )
    deps = RunnerDeps(FakeAdapter({"attacker": "1001", "victim": "1002"}, ["ok"] * 20),
                      FakeEvidenceSource([Facts(tool_calls=[
                          ObservedToolCall("get_portfolio", "1002", {}, "r")])] * 6))
    run_campaign([scenario], deps, storage=RunStorage(root), run_id="saved",
                 modes=["vulnerable"], profile_ref="genai-invest-stand@1.0.0", trials=trials)
    return root / "saved"


class RepeatFromRunTests(unittest.TestCase):
    def setUp(self):
        self.run_dir = saved_run(Path(tempfile.mkdtemp()))

    def test_saved_campaign_is_enough_to_preview_the_repeat(self):
        code, out = run_cli("run", "--from", str(self.run_dir), "--dry-run", "--json")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["campaign"]["profile"], "genai-invest-stand@1.0.0")
        self.assertEqual(payload["campaign"]["modes"], ["vulnerable"])
        scenario = payload["scenarios"][0]
        self.assertEqual(scenario["id"], "chain")
        self.assertEqual(scenario["payloads"], ["отрава"])
        self.assertEqual([s["kind"] for s in scenario["steps"]], ["payload", "message"])
        self.assertEqual(scenario["actor"], "1001")

    def test_trials_survive_the_round_trip(self):
        run_dir = saved_run(Path(tempfile.mkdtemp()), trials=3)
        transcript = (run_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(transcript), 3)
        code, out = run_cli("run", "--from", str(run_dir), "--dry-run", "--json")
        self.assertEqual(json.loads(out)["campaign"]["trials"], 3)

    def test_run_without_campaign_json_is_a_usage_error(self):
        empty = Path(tempfile.mkdtemp())
        code, out = run_cli("run", "--from", str(empty), "--dry-run", "--json")
        self.assertEqual(code, 2)
        self.assertIn("campaign.json", json.loads(out)["error"])

    def test_from_and_profile_together_are_refused(self):
        code, out = run_cli("run", "--from", str(self.run_dir), "--profile",
                            "genai-invest-stand@1.0.0", "--dry-run", "--json")
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])


if __name__ == "__main__":
    unittest.main()
