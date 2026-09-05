"""Streamlit-демо: те же данные, что у CLI, без собственной логики."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "agentic_redteam" / "ui" / "app.py"

FINDINGS = {
    "run_id": "20260905-000000-abcdef",
    "profile": "genai-invest-stand@1.0.0",
    "status": "completed",
    "modes": ["vulnerable"],
    "asr_percent": 100.0,
    "attempts_total": 1,
    "attempts_scored": 1,
    "attempts": [{"attempt": 1, "scenario_id": "bac-tool-argument", "attack_class": "cls",
                  "roles": "1001", "mode": "vulnerable", "verdict": "proven",
                  "signal": "инструмент обратился к принципалу 1002"}],
    "findings": [{"scenario_id": "bac-tool-argument", "attack_class": "cls",
                  "standard_refs": ["AML.T0012"], "verdict": "proven", "severity": "high",
                  "compromise_point": "принципал 1002", "chain_stage": "действие",
                  "evidence_refs": ["evidence-0001.json"]}],
    "limitations": [],
}


class StyleGuardTests(unittest.TestCase):
    def test_custom_font_does_not_override_streamlit_icon_font(self):
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn('[class*="st-"]', source)
        self.assertIn('[data-testid="stIconMaterial"]', source)
        self.assertIn('font-family:"Material Symbols Rounded" !important', source)

    def test_sidebar_expand_control_remains_reachable(self):
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn('[data-testid="stToolbar"] { visibility:hidden; }', source)
        self.assertIn('[data-testid="stExpandSidebarButton"]', source)
        self.assertIn('position:fixed!important; top:.75rem!important; left:.75rem!important', source)

    def test_ui_holds_no_campaign_logic_of_its_own(self):
        source = APP.read_text(encoding="utf-8")
        for leaked in ("run_pipeline", "auth_mode", "attacker_cus", "bundled_scenarios"):
            self.assertNotIn(leaked, source, leaked)
        self.assertIn("execute_campaign", source)


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "streamlit is not installed")
class CampaignScreenTests(unittest.TestCase):
    def _app(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(APP))
        app.run(timeout=30)
        self.assertEqual(app.exception, [])
        return app

    def test_screen_is_built_from_the_profile_registry(self):
        app = self._app()
        profile = next(w for w in app.selectbox if w.label == "Профиль")
        self.assertIn("genai-invest-stand@1.0.0", profile.options)
        scenarios = next(w for w in app.multiselect if w.label == "Сценарии")
        # Подпись каждого сценария несёт его достижимость — гейт покрытия виден
        # до запуска, как и в `profile coverage`.
        self.assertEqual(sorted(scenarios.options), [
            "bac-tool-argument · state",
            "mem-policy-conformant · state",
            "normal-own-portfolio · state",
            "poison-to-tool-chain · state",
            "system-prompt-leak · text · потолок indirect",
        ])
        modes = next(w for w in app.multiselect if w.label == "Режимы")
        self.assertEqual(sorted(modes.options), ["protected", "vulnerable"])

    def test_unreachable_scenarios_are_not_selected_by_default(self):
        app = self._app()
        scenarios = next(w for w in app.multiselect if w.label == "Сценарии")
        # На стенде источники есть у всех, кроме текстового — он всё равно запускаем.
        self.assertIn("bac-tool-argument", scenarios.value)

    def test_no_identity_or_provider_fields_remain(self):
        app = self._app()
        labels = [w.label for w in app.text_input] + [w.label for w in app.selectbox]
        for gone in ("CUS атакующего", "CUS цели", "Режим авторизации", "Сценарий"):
            self.assertNotIn(gone, labels)

    def test_preflight_uses_the_read_only_check(self):
        from streamlit.testing.v1 import AppTest
        from agentic_redteam.doctor import CheckResult
        with patch("agentic_redteam.evidence.calibrate.check",
                   return_value=[CheckResult("target", True, "доступен")]) as called, \
             patch("agentic_redteam.evidence.bundle.EvidenceBundle.from_profile"), \
             patch("agentic_redteam.adapters.http_chat.HttpChatAdapter.from_profile"):
            app = AppTest.from_file(str(APP)).run(timeout=30)
            next(b for b in app.button if b.label == "ПРОВЕРИТЬ").click()
            app.run(timeout=30)
        self.assertEqual(app.exception, [])
        self.assertEqual(called.call_count, 1)
        self.assertTrue(any("доступен" in item.value for item in app.markdown))

    def test_run_delegates_to_the_shared_campaign_core(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temporary:
            summary = {"run_id": FINDINGS["run_id"], "run_dir": temporary,
                       "scenarios": ["bac-tool-argument"], "skipped": [],
                       "asr_percent": 100.0, "findings": 1}
            with patch("agentic_redteam.app_cli.execute_campaign",
                       return_value=summary) as execute, \
                 patch("agentic_redteam.storage.runs.RunStorage.load_json",
                       return_value=FINDINGS), \
                 patch("agentic_redteam.app_cli.reporter_from_config", return_value=None):
                app = AppTest.from_file(str(APP)).run(timeout=30)
                next(b for b in app.button if b.label == "ЗАПУСТИТЬ").click()
                app.run(timeout=30)
            self.assertEqual(app.exception, [])
            self.assertEqual(execute.call_count, 1)
            self.assertTrue(any("COMPROMISED" in item.value for item in app.markdown))

    def test_skipped_scenarios_are_surfaced(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temporary:
            summary = {"run_id": FINDINGS["run_id"], "run_dir": temporary,
                       "scenarios": ["bac-tool-argument"],
                       "skipped": ["poison-to-tool-chain: нет tool_calls"],
                       "asr_percent": 0.0, "findings": 0}
            with patch("agentic_redteam.app_cli.execute_campaign", return_value=summary), \
                 patch("agentic_redteam.storage.runs.RunStorage.load_json",
                       return_value={**FINDINGS, "findings": [], "attempts": []}), \
                 patch("agentic_redteam.app_cli.reporter_from_config", return_value=None):
                app = AppTest.from_file(str(APP)).run(timeout=30)
                next(b for b in app.button if b.label == "ЗАПУСТИТЬ").click()
                app.run(timeout=30)
            self.assertEqual(app.exception, [])
            self.assertTrue(any("нет tool_calls" in item.value for item in app.warning))


class HelperTests(unittest.TestCase):
    def test_saved_result_accepts_the_current_findings_shape(self):
        from agentic_redteam.ui.app import _saved_result
        result = _saved_result(FINDINGS, Path("/tmp/run"))
        self.assertEqual(result["run_dir"], "/tmp/run")
        self.assertEqual(result["asr_percent"], 100.0)

    def test_saved_result_rejects_a_broken_document(self):
        from agentic_redteam.ui.app import _saved_result
        for broken in ({}, {"run_id": "r"}, {"run_id": "r", "status": "ok", "attempts": [1]}):
            with self.assertRaises(ValueError):
                _saved_result(broken, Path("/tmp/run"))



if __name__ == "__main__":
    unittest.main()
