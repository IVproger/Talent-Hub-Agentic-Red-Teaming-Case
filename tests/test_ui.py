"""Новый UI: онбординг из документов; своей логики кампании нет — делегирует ядру."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parents[1] / "agentic_redteam" / "ui" / "app.py"


class UiTests(unittest.TestCase):
    def test_module_imports_and_exposes_main(self):
        import agentic_redteam.ui.app as app
        self.assertTrue(callable(app.main))

    def test_profile_summary_reads_sections_and_rejected(self):
        import agentic_redteam.ui.app as app
        path = Path(tempfile.mkdtemp()) / "profile.yaml"
        path.write_text(yaml.safe_dump({
            "adapter": "http-chat",
            "identities": {"provider": "docker-exec-mint"},
            "surface": {"tools": [{"name": "t1"}], "memory": [{"id": "m1"}]},
            "evidence": [{"id": "e1", "provider": "log-regex"}],
            "modes": {"vulnerable": {}, "protected": {}},
            "ingest": {"judgement": {"rejected": [{"binding": "x", "reason": "y"}]}},
        }), encoding="utf-8")
        summary = app._profile_summary(str(path))
        self.assertEqual(summary["identities"], "docker-exec-mint")
        self.assertEqual(summary["tools"], ["t1"])
        self.assertEqual(summary["memory"], ["m1"])
        self.assertEqual(summary["evidence"], [("e1", "log-regex")])
        self.assertEqual(sorted(summary["modes"]), ["protected", "vulnerable"])
        self.assertEqual(len(summary["judgement"]), 1)

    def test_ui_delegates_to_shared_core_without_own_verdict_logic(self):
        source = APP.read_text(encoding="utf-8")
        # прогон и OWASP-сборка идут через общие функции ядра/CLI
        self.assertIn("execute_campaign", source)
        self.assertIn("build_baseline", source)
        # своей логики вердикта UI не держит (US-07 AC3)
        self.assertNotIn("def tool_principal_mismatch", source)
        self.assertNotIn("Grade.STATE", source)

    def test_target_is_endpoint_driven_not_a_hardcoded_registry(self):
        source = APP.read_text(encoding="utf-8")
        # цель задаётся base_url + документами, без выбора из реестра профилей
        self.assertIn("base_url", source)
        self.assertNotIn("ProfileRegistry", source)


if __name__ == "__main__":
    unittest.main()
