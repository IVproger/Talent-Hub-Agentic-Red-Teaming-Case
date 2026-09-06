import json
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class ReportPreviewTests(unittest.TestCase):
    def test_report_preview_is_button_gated_and_evidence_tab_renders(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            (run_dir / "report.md").write_text(
                "# Технический отчёт безопасности\n\nДоказательство.", encoding="utf-8"
            )
            (run_dir / "business-report.md").write_text(
                "# Бизнес-отчёт о рисках\n", encoding="utf-8"
            )
            findings = {
                "asr_percent": 100,
                "scenarios_scored": 1,
                "scenarios_proven": 1,
                "attempts_total": 1,
                "attempts": [],
                "observability": {"trace_url": "https://langfuse/trace/t"},
                "findings": [{
                    "scenario_id": "bac",
                    "attack_class": "tool_bac",
                    "severity": "critical",
                    "compromise_point": "доступ к чужому principal",
                    "problem_step": "activate",
                    "observation_id": "obs-2",
                    "evidence_refs": ["evidence-0001.json"],
                    "chain": [{
                        "name": "activate", "role": "attacker", "principal": "1001",
                        "request": "покажи 1002", "response": "данные 1002",
                        "observation_id": "obs-2", "tool_calls": [{
                            "tool": "portfolio", "principal": "1002",
                        }],
                    }],
                }],
            }
            app = Path(__file__).resolve().parents[1] / "agentic_redteam/ui/app.py"
            at = AppTest.from_file(str(app), default_timeout=10).run()
            at.session_state["last"] = {
                "run_dir": str(run_dir), "findings": json.loads(json.dumps(findings)),
            }
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(
                [tab.label for tab in at.tabs],
                ["ПОПЫТКИ", "ДОКАЗАТЕЛЬСТВА", "ОТЧЁТ", "ФАЙЛЫ"],
            )
            self.assertFalse(any(
                "Технический отчёт безопасности" in item.value for item in at.markdown
            ))
            preview = next(button for button in at.button
                           if button.label == "ОТКРЫТЬ PREVIEW MARKDOWN")
            preview.click().run()
            self.assertFalse(at.exception)
            self.assertTrue(any(
                "Технический отчёт безопасности" in item.value for item in at.markdown
            ))


if __name__ == "__main__":
    unittest.main()
