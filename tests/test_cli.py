from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_redteam.app_cli import build_parser, main
from agentic_redteam.llm import LLMRequestError
from agentic_redteam.pipeline import PipelineRunError


class CLITests(unittest.TestCase):
    def test_root_help(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit_:
            main(["--help"])
        self.assertEqual(exit_.exception.code, 0)
        self.assertIn("doctor", output.getvalue())
        self.assertIn("run", output.getvalue())
        self.assertNotIn("{doctor,run,poc", output.getvalue())

    def test_json_dry_run_has_one_document(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), contextlib.redirect_stdout(output):
            code = main(
                ["run", "--scenario", "generated-bac", "--dry-run", "--json"]
            )
        self.assertEqual(code, 0)
        parsed = json.loads(output.getvalue())
        self.assertTrue(parsed["dry_run"])
        self.assertEqual(parsed["configurations"][0]["scenario_id"], "generated-bac")
        self.assertNotIn("OPENROUTER_API_KEY\": \"sk-", output.getvalue())

    def test_num_zero_is_usage_error(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                [
                    "run",
                    "--scenario",
                    "generated-bac",
                    "--trials",
                    "0",
                    "--dry-run",
                    "--json",
                ]
            )
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_serve_rejects_public_bind(self):
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["serve", "--address", "0.0.0.0"])

    def test_provider_failure_has_stable_json_exit_code(self):
        output = io.StringIO()
        with patch(
            "agentic_redteam.app_cli.run_pipeline",
            side_effect=LLMRequestError("rate limit was reached"),
        ), contextlib.redirect_stdout(output):
            code = main(["run", "--scenario", "generated-bac", "--json"])
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(output.getvalue())["exit_code"], 4)

    def test_argparse_failure_is_one_json_document(self):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                main(["run", "--trials", "not-a-number", "--json"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(json.loads(output.getvalue())["exit_code"], 2)
        self.assertEqual(errors.getvalue(), "")

    def test_missing_scenario_is_usage_error(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["run", "--scenario", "/definitely/missing.yaml", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["exit_code"], 2)

    def test_pipeline_failure_includes_exit_code(self):
        output = io.StringIO()
        with patch(
            "agentic_redteam.app_cli.run_pipeline",
            side_effect=PipelineRunError("boom"),
        ), contextlib.redirect_stdout(output):
            code = main(["run", "--scenario", "generated-bac", "--json"])
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(output.getvalue())["exit_code"], 5)

    def test_semantically_invalid_scenario_is_usage_error_before_run(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            scenario = Path(temporary) / "invalid.yaml"
            scenario.write_text(
                """id: invalid
roles:
  attacker: {cus: '1001'}
params: {}
steps:
  - {name: activate, actor: missing, message: hello}
goal: []
""",
                encoding="utf-8",
            )
            with patch("agentic_redteam.app_cli.run_pipeline") as runner, \
                    contextlib.redirect_stdout(output):
                code = main(["run", "--scenario", str(scenario), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(runner.call_count, 0)
        self.assertEqual(json.loads(output.getvalue())["exit_code"], 2)

    def test_all_scenarios_are_validated_before_any_execution(self):
        output = io.StringIO()
        valid = Path(__file__).resolve().parents[1] / "agentic_redteam" / "scenarios" / "bac_tool_argument.yaml"
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "invalid.yaml"
            invalid.write_text(
                """id: invalid
roles:
  attacker: {cus: '1001'}
params: {}
steps:
  - {name: activate, actor: missing, message: hello}
goal: []
""",
                encoding="utf-8",
            )
            with patch("agentic_redteam.app_cli.run_pipeline") as runner, \
                    contextlib.redirect_stdout(output):
                code = main(
                    [
                        "run",
                        "--scenario",
                        str(valid),
                        "--scenario",
                        str(invalid),
                        "--json",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertEqual(runner.call_count, 0)

    def test_scenario_field_types_and_templates_are_validated(self):
        cases = (
            "  - {name: activate, actor: attacker, message: hello, finalize: 'false'}\n",
            "  - {name: activate, actor: attacker, message: '{x.missing}'}\n",
            "  - {name: activate, actor: attacker, message: hello}\n",
        )
        for steps in cases:
            output = io.StringIO()
            with self.subTest(steps=steps), tempfile.TemporaryDirectory() as temporary:
                scenario = Path(temporary) / "invalid.yaml"
                scenario.write_text(
                    "id: invalid\nroles:\n  attacker: {cus: '1001'}\n"
                    "params: {x: value}\nsteps:\n"
                    + steps
                    + "goal:\n  - {type: response_contains, step: activate, value: 5}\n",
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(output):
                    code = main(["run", "--scenario", str(scenario), "--json"])
            self.assertEqual(code, 2)

    def test_scenario_report_metadata_is_validated_before_execution(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            scenario = Path(temporary) / "invalid.yaml"
            scenario.write_text(
                """id: invalid
description: 42
atlas: 42
roles:
  attacker: {cus: '1001'}
params: {}
steps:
  - {name: activate, actor: attacker, message: hello}
goal: []
""",
                encoding="utf-8",
            )
            with patch("agentic_redteam.app_cli.run_pipeline") as runner, \
                    contextlib.redirect_stdout(output):
                code = main(["run", "--scenario", str(scenario), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(runner.call_count, 0)


if __name__ == "__main__":
    unittest.main()
