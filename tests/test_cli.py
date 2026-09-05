"""Контракт CLI: один JSON-документ, стабильные коды выхода, безопасный serve."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agentic_redteam.app_cli import build_parser, main


class CLIContractTests(unittest.TestCase):
    def test_root_help_lists_the_current_commands(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit_:
            main(["--help"])
        self.assertEqual(exit_.exception.code, 0)
        for command in ("doctor", "run", "profile", "report", "serve"):
            self.assertIn(command, output.getvalue())

    def test_run_without_a_profile_is_a_usage_error(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["run", "--json"])
        self.assertEqual(code, 2)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertIn("--profile", payload["error"])

    def test_zero_trials_is_a_usage_error(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["run", "--profile", "tests/data/profile_stand.yaml",
                         "--trials", "0", "--dry-run", "--json"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_argparse_failure_is_one_json_document(self):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                main(["run", "--trials", "not-a-number", "--json"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(json.loads(output.getvalue())["exit_code"], 2)
        self.assertEqual(errors.getvalue(), "")

    def test_serve_rejects_public_bind(self):
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["serve", "--address", "0.0.0.0"])

    def test_report_without_a_saved_run_is_a_usage_error(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["report", "--run", "/definitely/missing-run", "--json"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_report_rebuild_does_not_require_config_json_or_llm_config(self):
        run_dir = Path(tempfile.mkdtemp()) / "run"
        run_dir.mkdir()
        findings = {
            "run_id": "run", "profile": "p@1", "status": "completed",
            "modes": [], "asr_percent": 0.0, "attempts": [], "findings": [],
            "attempts_total": 0, "attempts_scored": 0, "limitations": [],
        }
        (run_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "report", "--run", str(run_dir), "--config",
                "/definitely/missing-config.yaml", "--json",
            ])
        self.assertEqual(code, 0, output.getvalue())
        self.assertTrue((run_dir / "report.md").is_file())

    def test_business_report_is_a_separate_deterministic_artifact(self):
        run_dir = Path(tempfile.mkdtemp()) / "run"
        run_dir.mkdir()
        findings = {
            "run_id": "run", "profile": "genai-invest-stand@1.0.0",
            "status": "completed", "modes": ["vulnerable"], "asr_percent": 100.0,
            "attempts": [], "attempts_total": 1, "attempts_scored": 1,
            "limitations": [],
            "findings": [{"scenario_id": "bac", "attack_class": "tool_bac",
                          "verdict": "proven", "severity": "critical",
                          "boundary": "cross_user", "evidence_refs": ["evidence-0001.json"]}],
        }
        (run_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["report", "--business", "--run", str(run_dir), "--json"])
        self.assertEqual(code, 0, output.getvalue())
        report = (run_dir / "business-report.md").read_text(encoding="utf-8")
        self.assertIn("Бизнес-отчёт", report)
        self.assertIn("Чтение данных другого клиента", report)
        self.assertFalse((run_dir / "report.md").exists())

    def test_report_rebuild_includes_saved_trace_link(self):
        run_dir = Path(tempfile.mkdtemp()) / "run"
        run_dir.mkdir()
        findings = {
            "run_id": "run", "profile": "p@1", "status": "completed",
            "modes": [], "asr_percent": 0.0, "attempts": [], "findings": [],
            "attempts_total": 0, "attempts_scored": 0, "limitations": [],
        }
        (run_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
        (run_dir / "observability.json").write_text(json.dumps({
            "trace_id": "trace-1", "trace_url": "http://langfuse.local/trace-1",
            "root_observation_id": "root-1",
        }), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["report", "--run", str(run_dir), "--json"])
        self.assertEqual(code, 0)
        report = (run_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("trace-1", report)
        self.assertIn("http://langfuse.local/trace-1", report)


if __name__ == "__main__":
    unittest.main()
