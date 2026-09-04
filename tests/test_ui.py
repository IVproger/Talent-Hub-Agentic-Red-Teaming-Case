from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "streamlit is not installed")
class StreamlitSmokeTests(unittest.TestCase):
    def test_custom_font_does_not_override_streamlit_icon_font(self):
        app_path = Path(__file__).resolve().parents[1] / "agentic_redteam" / "ui" / "app.py"
        source = app_path.read_text(encoding="utf-8")
        self.assertNotIn('[class*="st-"]', source)
        self.assertIn('[data-testid="stIconMaterial"]', source)
        self.assertIn('font-family:"Material Symbols Rounded" !important', source)

    def test_sidebar_expand_control_remains_reachable(self):
        app_path = Path(__file__).resolve().parents[1] / "agentic_redteam" / "ui" / "app.py"
        source = app_path.read_text(encoding="utf-8")
        self.assertNotIn('[data-testid="stToolbar"] { visibility:hidden; }', source)
        self.assertIn('[data-testid="stExpandSidebarButton"]', source)
        self.assertIn('position:fixed!important; top:.75rem!important; left:.75rem!important', source)

    def test_app_renders_without_starting_a_run(self):
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parents[1] / "agentic_redteam" / "ui" / "app.py"
        app = AppTest.from_file(str(app_path))
        app.run(timeout=15)
        self.assertEqual(app.exception, [])
        self.assertTrue(any("Agentic Red Team" in item.value for item in app.markdown))
        scenario_select = next(
            widget for widget in app.selectbox if widget.label == "Сценарий"
        )
        self.assertEqual(len(scenario_select.options), 5)
        self.assertFalse(
            any("Провайдер" in widget.label for widget in app.selectbox)
        )
        self.assertFalse(any("Модель" in widget.label for widget in app.text_input))
        self.assertTrue(
            any("config/target.yaml" in item.value for item in app.markdown)
        )
        scenario_select.set_value("poison-to-tool-chain").run(timeout=15)
        self.assertEqual(app.exception, [])
        self.assertTrue(
            any("poison-to-tool-chain" in item.value for item in app.markdown)
        )

    def test_config_fingerprint_changes_with_effective_inputs(self):
        from agentic_redteam.llm import default_role_configs
        from agentic_redteam.ui.app import (
            _config_fingerprint,
            _scenario_catalog,
            checks_ok_from_dicts,
        )

        roles = default_role_configs()
        first = _config_fingerprint(roles, "1001", "1002", 5, "vulnerable")
        second = _config_fingerprint(roles, "1001", "1002", 6, "vulnerable")
        third = _config_fingerprint(
            roles,
            "1001",
            "1002",
            5,
            "vulnerable",
            target_context={"config_sha256": "changed"},
        )
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertNotEqual(
            first,
            _config_fingerprint(
                roles,
                "1001",
                "1002",
                5,
                "vulnerable",
                scenario_id="bac-tool-argument",
            ),
        )
        self.assertEqual(
            set(_scenario_catalog()),
            {
                "generated-bac",
                "bac-tool-argument",
                "mem-policy-conformant",
                "poison-to-tool-chain",
                "system-prompt-leak",
            },
        )
        self.assertTrue(checks_ok_from_dicts([{"ok": True, "blocking": True}]))
        self.assertFalse(checks_ok_from_dicts([{"ok": False, "blocking": True}]))

    def test_trace_link_accepts_only_safe_http_urls(self):
        from agentic_redteam.ui.app import _safe_trace_url

        self.assertEqual(
            _safe_trace_url("http://localhost:3001/project/p/traces/t"),
            "http://localhost:3001/project/p/traces/t",
        )
        self.assertIsNone(_safe_trace_url("javascript:alert(1)"))
        self.assertIsNone(_safe_trace_url("https://user:secret@example.test/trace"))

    def test_preflight_then_run_executes_pipeline_once(self):
        from agentic_redteam.doctor import CheckResult
        from agentic_redteam.pipeline import RunResult
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parents[1] / "agentic_redteam" / "ui" / "app.py"
        with tempfile.TemporaryDirectory() as temporary, patch(
            "agentic_redteam.doctor.run_checks",
            return_value=[CheckResult("ready", True, "Ready")],
        ), patch(
            "agentic_redteam.pipeline.run_pipeline",
            return_value=RunResult(
                run_id="run-ui-test",
                status="completed",
                run_dir=temporary,
                attacker_cus="1001",
                victim_cus="1002",
            ),
        ) as pipeline, patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            app = AppTest.from_file(str(app_path)).run(timeout=15)
            app.session_state.run_error = "stale error"
            next(button for button in app.button if button.label == "ПРОВЕРИТЬ").click()
            app.run(timeout=15)
            self.assertFalse(any("stale error" in item.value for item in app.error))
            run_button = next(
                button for button in app.button if button.label == "ЗАПУСТИТЬ"
            )
            self.assertFalse(run_button.disabled)
            # Adaptive BAC requires target context; fill both fields first.
            for area in app.text_area:
                if area.label in ("Архитектура", "Описание компонентов"):
                    area.set_value("stub context")
            run_button.click()
            app.run(timeout=15)
            self.assertTrue(
                any("NOT SCORED" in item.value for item in app.markdown)
            )
        self.assertEqual(pipeline.call_count, 1)

    def test_empty_context_blocks_adaptive_bac_run(self):
        from agentic_redteam.doctor import CheckResult
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parents[1] / "agentic_redteam" / "ui" / "app.py"
        with patch(
            "agentic_redteam.doctor.run_checks",
            return_value=[CheckResult("ready", True, "Ready")],
        ), patch(
            "agentic_redteam.pipeline.run_pipeline"
        ) as pipeline, patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            app = AppTest.from_file(str(app_path)).run(timeout=15)
            next(button for button in app.button if button.label == "ПРОВЕРИТЬ").click()
            app.run(timeout=15)
            run_button = next(
                button for button in app.button if button.label == "ЗАПУСТИТЬ"
            )
            run_button.click()
            app.run(timeout=15)
        self.assertEqual(pipeline.call_count, 0)
        self.assertTrue(app.session_state.arch_error)
        self.assertTrue(app.session_state.card_error)
        self.assertTrue(
            any("схему архитектуры" in item.value for item in app.error)
        )


if __name__ == "__main__":
    unittest.main()
