"""run --profile без --dry-run: реальные адаптер и evidence через CLI."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_redteam.app_cli import main
from agentic_redteam.normalize.facts import Facts, ObservedToolCall
from tests.fakes import FakeAdapter, FakeEvidenceSource


PROFILE = "tests/data/profile_stand.yaml"


class Bundle(FakeEvidenceSource):
    """Стоит на месте EvidenceBundle: тот же шов плюс гейт и close."""

    def __init__(self, facts, capabilities=("tool_calls", "memory_snapshot", "session_reset")):
        super().__init__(facts)
        self._capabilities = frozenset(capabilities)
        self.closed = False

    def capabilities(self):
        return self._capabilities

    def supports(self, goal):
        missing = [] if "tool_calls" in self._capabilities else ["нет tool_calls"]
        return not missing, missing

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class Adapter(FakeAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed = False

    def close(self):
        self.closed = True


def hit(principal="1002"):
    return Facts(tool_calls=[ObservedToolCall("get_portfolio", principal, {}, "raw")])


def run_cli(argv, bundle, adapter=None):
    adapter = adapter or Adapter({"attacker": "1001", "victim": "1002"}, ["ok"] * 40)
    output = io.StringIO()
    with patch("agentic_redteam.app_cli.EvidenceBundle") as bundle_cls, \
         patch("agentic_redteam.app_cli.HttpChatAdapter") as adapter_cls, \
         patch("agentic_redteam.app_cli.reporter_from_config", return_value=None), \
         contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
        bundle_cls.from_profile.return_value = bundle
        adapter_cls.from_profile.return_value = adapter
        code = main(list(argv))
    return code, output.getvalue(), adapter


class ExecuteCampaignTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()

    def _run(self, *extra, bundle=None):
        bundle = bundle or Bundle([hit()] * 8)
        code, out, adapter = run_cli(
            ["run", "--profile", PROFILE, "--scenario", "bac-tool-argument",
             "--mode", "vulnerable", "--output", self.out, "--json", *extra], bundle)
        return code, out, bundle, adapter

    def test_campaign_runs_and_writes_its_artifacts(self):
        code, out, bundle, adapter = self._run()
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        run_dir = Path(payload["run"]["run_dir"])
        for name in ("campaign.json", "transcript.jsonl", "findings.json",
                     "report.md", "status.json"):
            self.assertTrue((run_dir / name).exists(), name)
        self.assertEqual(payload["run"]["asr_percent"], 100.0)

    def test_verdict_comes_from_the_collected_state(self):
        code, out, _, _ = self._run(bundle=Bundle([Facts(tool_calls=[
            ObservedToolCall("get_portfolio", "1001", {}, "raw")])] * 8))
        payload = json.loads(out)
        self.assertEqual(payload["run"]["asr_percent"], 0.0)
        self.assertEqual(payload["run"]["findings"], 0)

    def test_adapter_and_bundle_are_closed(self):
        _, _, bundle, adapter = self._run()
        self.assertTrue(bundle.closed)
        self.assertTrue(adapter.closed)

    def test_scenario_without_its_source_is_excluded_not_failed(self):
        bundle = Bundle([hit()] * 8, capabilities=("memory_snapshot",))
        code, out, _, _ = self._run(bundle=bundle)
        self.assertEqual(code, 2)
        error = json.loads(out)["error"]
        self.assertIn("bac-tool-argument", error)
        self.assertIn("tool_calls", error)

    def test_partial_gate_runs_what_is_supported_and_says_what_it_skipped(self):
        class Partial(Bundle):
            def supports(self, goal):
                text_only = all(a["type"] == "response_contains" for a in goal)
                return (False, ["нет tool_calls"]) if not text_only else (True, [])

        bundle = Partial([hit()] * 8)
        code, out, _ = run_cli(
            ["run", "--profile", PROFILE, "--scenario", "all", "--mode", "vulnerable",
             "--output", self.out, "--json"], bundle)
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["run"]["scenarios"], ["system-prompt-leak"])
        self.assertIn("bac-tool-argument", " ".join(payload["run"]["skipped"]))

    def test_memory_commit_step_without_the_feature_is_refused_up_front(self):
        """Иначе фича, которой нет, сделала бы error каждой попытки, а не отказ."""
        bundle = Bundle([hit()] * 8)
        code, out, _ = run_cli(
            ["run", "--profile", PROFILE, "--scenario", "poison-to-tool-chain",
             "--mode", "vulnerable", "--output", self.out, "--json"], bundle)
        self.assertEqual(code, 2)
        error = json.loads(out)["error"]
        self.assertIn("poison-to-tool-chain", error)
        self.assertIn("commit_memory", error)

    def test_scenario_without_a_commit_step_runs_without_the_feature(self):
        code, out, _, _ = self._run()
        self.assertEqual(code, 0, out)

    def test_reset_without_a_source_is_refused_before_the_target_is_touched(self):
        bundle = Bundle([hit()] * 8, capabilities=("tool_calls", "memory_snapshot"))
        code, out, _, adapter = self._run(bundle=bundle)
        self.assertEqual(code, 2)
        self.assertIn("reset", json.loads(out)["error"])


if __name__ == "__main__":
    unittest.main()
