"""profile check/verify и doctor --profile поверх калибровки 3.7."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from agentic_redteam.app_cli import main
from agentic_redteam.doctor import CheckResult


PROFILE = "tests/data/profile_stand.yaml"


class Bundle:
    def __init__(self):
        self.closed = False
        self.providers = {}

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class Adapter:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def run_cli(argv, results, calibrator="check"):
    bundle, adapter = Bundle(), Adapter()
    output = io.StringIO()
    with patch("agentic_redteam.app_cli.EvidenceBundle") as bundle_cls, \
         patch("agentic_redteam.app_cli.HttpChatAdapter") as adapter_cls, \
         patch(f"agentic_redteam.app_cli.{calibrator}", return_value=results) as called, \
         contextlib.redirect_stdout(output):
        bundle_cls.from_profile.return_value = bundle
        adapter_cls.from_profile.return_value = adapter
        code = main(list(argv))
    return code, output.getvalue(), called, bundle, adapter


OK = [CheckResult("target", True, "доступен"),
      CheckResult("tool_calls", True, "источник подтверждён")]
MEMORY_DOWN = [CheckResult("target", True, "доступен"),
               CheckResult("memory:policy", False, "снимок недоступен", blocking=False)]
TARGET_DOWN = [CheckResult("target", False, "цель недоступна")]


class ProfileCheckTests(unittest.TestCase):
    def test_check_reports_every_source(self):
        code, out, called, bundle, adapter = run_cli(
            ["profile", "check", "--profile", PROFILE, "--json"], OK)
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual([c["name"] for c in payload["checks"]], ["target", "tool_calls"])
        self.assertEqual(called.call_count, 1)
        self.assertTrue(bundle.closed)
        self.assertTrue(adapter.closed)

    def test_unreachable_memory_is_not_blocking(self):
        code, out, _, _, _ = run_cli(
            ["profile", "check", "--profile", PROFILE, "--json"], MEMORY_DOWN)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])

    def test_unreachable_target_is_a_preflight_failure(self):
        code, out, _, _, _ = run_cli(
            ["profile", "check", "--profile", PROFILE, "--json"], TARGET_DOWN)
        self.assertEqual(code, 3)
        self.assertFalse(json.loads(out)["ok"])

    def test_human_output_marks_each_check(self):
        code, out, _, _, _ = run_cli(["profile", "check", "--profile", PROFILE], MEMORY_DOWN)
        self.assertEqual(code, 0)
        self.assertIn("ок", out)
        self.assertIn("сбой", out)
        self.assertIn("снимок недоступен", out)


class ProfileVerifyTests(unittest.TestCase):
    def test_verify_runs_the_visibility_probe(self):
        code, out, called, bundle, adapter = run_cli(
            ["profile", "verify", "--profile", PROFILE, "--json"], OK, calibrator="verify")
        self.assertEqual(code, 0, out)
        self.assertEqual(called.call_count, 1)
        self.assertTrue(bundle.closed)
        self.assertTrue(adapter.closed)

    def test_verify_says_it_changes_state(self):
        code, out, _, _, _ = run_cli(
            ["profile", "verify", "--profile", PROFILE], OK, calibrator="verify")
        self.assertIn("меняет состояние", out)


class DoctorProfileTests(unittest.TestCase):
    def test_doctor_with_a_profile_uses_the_read_only_check(self):
        code, out, called, _, _ = run_cli(
            ["doctor", "--profile", PROFILE, "--json"], OK)
        self.assertEqual(code, 0, out)
        self.assertEqual(called.call_count, 1)
        self.assertEqual([c["name"] for c in json.loads(out)["checks"]],
                         ["target", "tool_calls"])


if __name__ == "__main__":
    unittest.main()
