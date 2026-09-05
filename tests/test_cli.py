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


if __name__ == "__main__":
    unittest.main()
