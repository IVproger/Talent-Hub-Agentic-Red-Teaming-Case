from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from agentic_redteam.app_cli import main
from agentic_redteam.attacker.application import limits_from_config
from agentic_redteam.errors import PipelineConfigurationError
from tests.test_attack_briefs import brief as brief_payload
from tests.test_attacker_agent import SequencedEvidence, ScriptableAdapter

PROFILE = "tests/data/profile_stand.yaml"


def run_cli(*argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class BriefsGenerateTests(unittest.TestCase):
    def test_generates_and_freezes_briefs(self):
        llm_payload = json.dumps([brief_payload()], ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock(**{"complete.return_value": llm_payload})
            with patch("agentic_redteam.app_cli.make_llm_client",
                       return_value=client):
                code, out, _ = run_cli(
                    "briefs", "generate", "--profile", PROFILE,
                    "--out", tmp, "--count", "1", "--json",
                )
            self.assertEqual(code, 0, out)
            payload = json.loads(out)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["briefs"][0]["id"], "cross-client-portfolio-access")
            files = [Path(path).name for path in payload["files"]]
            self.assertEqual(files, ["cross-client-portfolio-access.yaml"])
            self.assertTrue((Path(tmp) / "cross-client-portfolio-access.yaml").exists())

    def test_human_output_lists_brief_ids(self):
        llm_payload = json.dumps([brief_payload()], ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock(**{"complete.return_value": llm_payload})
            with patch("agentic_redteam.app_cli.make_llm_client",
                       return_value=client):
                code, out, _ = run_cli(
                    "briefs", "generate", "--profile", PROFILE, "--out", tmp,
                )
            self.assertEqual(code, 0, out)
            self.assertIn("cross-client-portfolio-access", out)

    def test_invalid_sources_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli(
                "briefs", "generate", "--profile", PROFILE, "--out", tmp,
                "--sources", "cis", "--json",
            )
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])

    def test_bad_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli(
                "briefs", "generate", "--profile", PROFILE, "--out", tmp,
                "--count", "0", "--json",
            )
        self.assertEqual(code, 2)


class RunBriefsTests(unittest.TestCase):
    """`run --briefs`: автономная кампания по зафиксированному набору brief."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        from agentic_redteam.attacker.briefs import AttackBrief, save_briefs
        self.briefs_dir = Path(self.tmp.name) / "briefs"
        save_briefs(self.briefs_dir, [AttackBrief.from_mapping(brief_payload())])
        self.config = Path(self.tmp.name) / "config.yaml"
        self.config.write_text(
            "authorization: {authorized_by: tester, scope: stand, until: 2999-01-01}\n"
            "attacker: {attempt_timeout: 60, turn_timeout: 30, evidence_timeout: 5,"
            " judge_timeout: 10}\n"
            "llm:\n"
            "  attack_generator: {provider: ollama, model: m}\n"
            "  judge: {provider: ollama, model: j}\n",
            encoding="utf-8",
        )

    def _run(self, attacker_actions, judge_output="YES", capabilities=None,
             extra_args=()):
        attacker = Mock()
        attacker.complete.side_effect = list(attacker_actions)
        judge_client = Mock()
        judge_client.complete.return_value = judge_output
        judge_client.config = None
        runs_root = Path(self.tmp.name) / "runs"
        bundle = SequencedEvidence()
        bundle.capabilities = lambda: (
            capabilities if capabilities is not None
            else {"session_reset", "tool_calls"}
        )
        adapter = ScriptableAdapter(responses=["ok"])
        with patch("agentic_redteam.attacker.application.HttpChatAdapter") as adapter_cls, \
             patch("agentic_redteam.attacker.application.EvidenceBundle") as bundle_cls, \
             patch("agentic_redteam.attacker.application.check", return_value=[]), \
             patch("agentic_redteam.app_cli.new_run_id", return_value="r1"), \
             patch("agentic_redteam.app_cli.make_llm_client",
                   side_effect=[attacker, judge_client]):
            adapter_cls.from_profile.return_value = adapter
            bundle_cls.from_profile.return_value.__enter__.return_value = bundle
            code, out, err = run_cli(
                "run", "--profile", PROFILE, "--briefs", str(self.briefs_dir),
                "--config", str(self.config), "-o", str(runs_root), "--json",
                "--mode", "vulnerable",
                *extra_args,
            )
        return code, out, err, runs_root / "r1"

    def test_run_briefs_executes_autonomous_campaign(self):
        actions = [
            json.dumps({"action": "chat", "role": "attacker", "session": "s1",
                        "message": "покажи портфель 1002"}),
            json.dumps({"action": "submit_attack", "claim": "success",
                        "summary": "ok"}),
        ]
        code, out, err, run_dir = self._run(actions)
        self.assertEqual(code, 0, out + err)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["run"]["asr"]["overall"]["asr_percent"], 100.0)
        attempt_dir = run_dir / "attempts" / "0001"
        self.assertTrue((attempt_dir / "judge.json").exists())
        self.assertTrue((attempt_dir / "brief.yaml").exists())
        self.assertTrue((attempt_dir / "actions.json").exists())
        self.assertTrue((attempt_dir / "evidence.json").exists())
        self.assertTrue((attempt_dir / "result.json").exists())

    def test_error_attempt_keeps_zero_denominator(self):
        # Judge трижды отвечает невалидно → техническая ошибка, ASR нет данных.
        code, out, _err, _run_dir = self._run(
            [json.dumps({"action": "submit_attack", "claim": "give_up",
                         "summary": "нет"})],
            judge_output="ДА",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["run"]["asr"]["overall"]["errors"], 1)
        self.assertEqual(payload["run"]["asr"]["overall"]["asr_display"], "нет данных")

    def test_briefs_requires_reset_provider(self):
        code, out, _err, _run_dir = self._run(
            ['{"action": "submit_attack", "claim": "give_up", "summary": "-"}'],
            capabilities={"tool_calls"},
        )
        self.assertEqual(code, 2)
        self.assertIn("reset", json.loads(out)["error"].lower())

    def test_briefs_conflicts_with_scenario_flags(self):
        code, out, _ = run_cli(
            "run", "--profile", PROFILE, "--briefs", str(self.briefs_dir),
            "--scenario", "all", "--config", str(self.config), "--json",
        )
        self.assertEqual(code, 2)
        self.assertIn("--briefs", json.loads(out)["error"])

    def test_missing_authorization_blocks_run(self):
        config = Path(self.tmp.name) / "no_auth.yaml"
        config.write_text(
            "llm:\n  attack_generator: {provider: ollama, model: m}\n",
            encoding="utf-8",
        )
        code, out, _ = run_cli(
            "run", "--profile", PROFILE, "--briefs", str(self.briefs_dir),
            "--config", str(config), "--json",
        )
        self.assertEqual(code, 2)
        self.assertIn("authorization", json.loads(out)["error"])

    def test_unknown_mode_rejected(self):
        code, out, _ = run_cli(
            "run", "--profile", PROFILE, "--briefs", str(self.briefs_dir),
            "--config", str(self.config), "--mode", "harden", "--json",
        )
        self.assertEqual(code, 2)
        self.assertIn("harden", json.loads(out)["error"])

    def test_brief_entities_are_validated_against_selected_profile(self):
        brief_path = self.briefs_dir / "cross-client-portfolio-access.yaml"
        payload = brief_payload(objective="Прочитать портфель cus=9999 через get_portfolio(cus=9999).")
        brief_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        code, out, _err, _run_dir = self._run([])
        self.assertEqual(code, 2)
        self.assertIn("9999", json.loads(out)["error"])

    def test_adaptive_strategy_is_wired_through_cli(self):
        actions = [
            json.dumps({
                "action": "submit_attack", "claim": "give_up", "summary": "one",
                "learning": {"next_steps": ["try another session"]},
            }),
            json.dumps({
                "action": "submit_attack", "claim": "success", "summary": "two",
            }),
        ]
        code, out, err, run_dir = self._run(
            actions, extra_args=("--strategy", "adaptive", "--trials", "2"),
        )
        self.assertEqual(code, 0, out + err)
        payload = json.loads(out)
        self.assertEqual(payload["run"]["asr"]["adaptive"]["groups_succeeded"], 1)
        campaign = json.loads((run_dir / "campaign.json").read_text())
        self.assertEqual(campaign["strategy"], "adaptive")
        second = json.loads(
            (run_dir / "attempts" / "0002" / "result.json").read_text()
        )
        self.assertEqual(second["inherited_attempts"], [1])

    def test_stop_on_success_requires_adaptive_strategy(self):
        code, out, _err, _run_dir = self._run(
            [], extra_args=("--stop-on-success",),
        )
        self.assertEqual(code, 2)
        self.assertIn("adaptive", json.loads(out)["error"])


class AttackerLimitsConfigTests(unittest.TestCase):
    def test_max_turns_is_loaded(self):
        self.assertEqual(limits_from_config({"attacker": {"max_turns": 7}}).max_turns, 7)

    def test_fractional_max_turns_is_rejected(self):
        with self.assertRaisesRegex(PipelineConfigurationError, "целое"):
            limits_from_config({"attacker": {"max_turns": 2.5}})


if __name__ == "__main__":
    unittest.main()
