import json, tempfile, unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from agentic_redteam.app_cli import execute_agentic_campaign, _config_mapping, load_profile

PROFILE = "tests/data/profile_stand.yaml"
CONFIG = "config/target.yaml"


class ExecuteAgenticCampaignTests(unittest.TestCase):
    def _run(self, tmp):
        profile = load_profile(PROFILE)
        config = _config_mapping(CONFIG)
        captured = {}

        def fake_campaign(agent, adapter, evidence, scenarios, **kw):
            captured["scenarios"] = list(scenarios)
            return {"asr_percent": 100.0, "scenarios_scored": 1,
                    "scenarios_proven": 1, "attempts_total": 1,
                    "attempts": [{"scenario_id": "agentic-x", "attack_class": "X",
                                  "verdict": "proven", "target": "x", "steps": []}]}

        with patch("agentic_redteam.app_cli.make_llm_client", return_value=Mock()), \
             patch("agentic_redteam.app_cli.generate",
                   side_effect=lambda scn, *a, **k: [f"seed-{scn.goal[0]['type']}"]), \
             patch("agentic_redteam.app_cli.HttpChatAdapter") as adapter_cls, \
             patch("agentic_redteam.app_cli.EvidenceBundle") as bundle_cls, \
             patch("agentic_redteam.app_cli.run_agentic_campaign", side_effect=fake_campaign):
            adapter_cls.from_profile.return_value = Mock()
            bundle_cls.from_profile.return_value = MagicMock()
            summary = execute_agentic_campaign(
                profile, config, tmp, "20260906-000000-test", budget=3)
        return summary, captured

    def test_seeds_are_generated_and_attached_to_each_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            _summary, captured = self._run(tmp)
            self.assertTrue(captured["scenarios"])
            for scn in captured["scenarios"]:
                self.assertEqual(scn.seed, f"seed-{scn.goal[0]['type']}")

    def test_findings_and_report_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary, _ = self._run(tmp)
            run_dir = Path(summary["run_dir"])
            findings = json.loads((run_dir / "findings.json").read_text())
            self.assertEqual(findings["asr_percent"], 100.0)
            self.assertIn("authorization", findings)
            self.assertTrue((run_dir / "report.md").read_text())

    def test_timings_recorded_with_phases_and_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile(PROFILE)
            config = _config_mapping(CONFIG)
            with patch("agentic_redteam.app_cli.make_llm_client", return_value=Mock()), \
                 patch("agentic_redteam.app_cli.generate", side_effect=lambda scn, *a, **k: ["seed"]), \
                 patch("agentic_redteam.app_cli.HttpChatAdapter") as adapter_cls, \
                 patch("agentic_redteam.app_cli.EvidenceBundle") as bundle_cls, \
                 patch("agentic_redteam.app_cli.run_agentic_campaign",
                       return_value={"asr_percent": 0.0, "scenarios_scored": 0,
                                     "scenarios_proven": 0, "attempts_total": 0, "attempts": []}):
                adapter_cls.from_profile.return_value = Mock()
                bundle_cls.from_profile.return_value = MagicMock()
                summary = execute_agentic_campaign(
                    profile, config, tmp, "20260906-000001-t", budget=2,
                    extra_phases=[{"name": "Создание профиля", "seconds": 1.5}])
            timings = summary["findings"]["timings"]
            names = [p["name"] for p in timings["phases"]]
            self.assertEqual(names[0], "Создание профиля")   # проброшенная фаза — первой
            self.assertIn("Генерация атак", names)
            self.assertIn("Атака (ReAct)", names)
            self.assertAlmostEqual(timings["total_seconds"],
                                   round(sum(p["seconds"] for p in timings["phases"]), 3), places=3)

    def test_cancelled_run_marks_status_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile(PROFILE)
            config = _config_mapping(CONFIG)
            with patch("agentic_redteam.app_cli.make_llm_client", return_value=Mock()), \
                 patch("agentic_redteam.app_cli.generate", side_effect=lambda scn, *a, **k: ["seed"]), \
                 patch("agentic_redteam.app_cli.HttpChatAdapter") as adapter_cls, \
                 patch("agentic_redteam.app_cli.EvidenceBundle") as bundle_cls, \
                 patch("agentic_redteam.app_cli.run_agentic_campaign",
                       return_value={"asr_percent": 0.0, "scenarios_scored": 0,
                                     "scenarios_proven": 0, "attempts_total": 0, "attempts": []}):
                adapter_cls.from_profile.return_value = Mock()
                bundle_cls.from_profile.return_value = MagicMock()
                summary = execute_agentic_campaign(
                    profile, config, tmp, "20260906-000002-c", budget=2, should_stop=lambda: True)
            status = json.loads((Path(summary["run_dir"]) / "status.json").read_text())
            self.assertEqual(status["status"], "interrupted")

    def test_status_json_written_so_run_is_listable(self):
        # list_runs() опирается на status.json — без него агентный прогон в
        # истории будет «invalid» и не откроется
        with tempfile.TemporaryDirectory() as tmp:
            summary, _ = self._run(tmp)
            run_dir = Path(summary["run_dir"])
            status = json.loads((run_dir / "status.json").read_text())
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["run_id"], run_dir.name)
            self.assertEqual(status["asr_percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
