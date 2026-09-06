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

    def test_find_openapi_picks_paths_doc_not_compose(self):
        import agentic_redteam.ui.app as app
        tmp = Path(tempfile.mkdtemp())
        compose = tmp / "docker-compose.yml"
        compose.write_text("services:\n  mongo: {}\n", encoding="utf-8")
        openapi = tmp / "openapi.json"
        openapi.write_text('{"openapi":"3.0.0","paths":{"/x":{}}}', encoding="utf-8")
        arch = tmp / "arch.mmd"
        arch.write_text("graph TD;", encoding="utf-8")
        self.assertEqual(app._find_openapi([compose, arch, openapi]), openapi)
        self.assertIsNone(app._find_openapi([compose, arch]))

    def test_ui_delegates_to_shared_core_without_own_verdict_logic(self):
        source = APP.read_text(encoding="utf-8")
        # прогон идёт через общее ядро CLI
        self.assertIn("execute_agentic_campaign", source)
        # своей логики вердикта UI не держит (US-07 AC3)
        self.assertNotIn("def tool_principal_mismatch", source)
        self.assertNotIn("Grade.STATE", source)

    def test_only_run_button_no_check_or_build(self):
        source = APP.read_text(encoding="utf-8")
        # единственное действие — «ЗАПУСК»; «ПРОВЕРКА»/«СОБРАТЬ ПРОФИЛЬ» убраны
        self.assertIn("ЗАПУСК", source)
        self.assertNotIn("ПРОВЕРКА", source)
        self.assertNotIn("СОБРАТЬ ПРОФИЛЬ", source)

    def test_run_is_async_with_autorefresh(self):
        source = APP.read_text(encoding="utf-8")
        # прогон в фоновом потоке + авто-обновление статуса
        self.assertIn("threading", source)
        self.assertIn("run_every", source)

    def test_timings_tab_present(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("ТАЙМИНГИ", source)

    def test_run_history_panel_is_present(self):
        source = APP.read_text(encoding="utf-8")
        # история прогонов: список из runs/ (мастер-деталь) + открытие сохранённого
        self.assertIn("list_runs", source)
        self.assertIn("history_open", source)

    def test_sections_are_a_segmented_switch_not_radio(self):
        source = APP.read_text(encoding="utf-8")
        # разделы — сегмент-переключатель (программно выбираемый), не radio
        self.assertIn("st.segmented_control", source)
        self.assertIn('"ЗАПУСК", "ИСТОРИЯ"', source)
        self.assertNotIn('st.radio("Раздел"', source)

    def test_target_is_endpoint_driven_not_a_hardcoded_registry(self):
        source = APP.read_text(encoding="utf-8")
        # цель задаётся base_url + документами, без выбора из реестра профилей
        self.assertIn("base_url", source)
        self.assertNotIn("ProfileRegistry", source)


if __name__ == "__main__":
    unittest.main()
