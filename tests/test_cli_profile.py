"""profile-подкоманды: список, карта поверхности, диф версий, гейт покрытия."""
from __future__ import annotations

import contextlib
import io
import json
import unittest

from agentic_redteam.app_cli import main


STAND = "tests/data/profile_stand.yaml"
DVAA = "tests/data/profile_dvaa.yaml"


def run_cli(*argv) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(list(argv))
    return code, output.getvalue()


class ProfileListShowTests(unittest.TestCase):
    def test_list_prints_name_and_version(self):
        code, out = run_cli("profile", "list", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn(["genai-invest-stand", "1.0.0"], json.loads(out)["profiles"])

    def test_show_renders_the_surface_map(self):
        code, out = run_cli("profile", "show", "--profile", STAND, "--json")
        self.assertEqual(code, 0, out)
        surface = json.loads(out)["profile"]
        self.assertEqual(surface["name"], "genai-invest-stand")
        self.assertEqual([t["name"] for t in surface["tools"]], ["get_portfolio"])
        self.assertEqual([m["id"] for m in surface["memory"]], ["policy", "semantic"])
        self.assertEqual([b["id"] for b in surface["isolation"]], ["user", "session"])
        self.assertEqual(sorted(surface["modes"]), ["protected", "vulnerable"])

    def test_show_human_output_names_the_tool_and_boundary(self):
        code, out = run_cli("profile", "show", "--profile", STAND)
        self.assertEqual(code, 0)
        self.assertIn("get_portfolio", out)
        self.assertIn("данные одного клиента не видны другому", out)


class ProfileDiffTests(unittest.TestCase):
    def test_diff_reports_sections_that_changed(self):
        code, out = run_cli("profile", "diff", STAND, DVAA, "--json")
        self.assertEqual(code, 0, out)
        difference = json.loads(out)["diff"]
        self.assertIn("tools", difference)
        self.assertIn("entrypoint", difference)

    def test_identical_profiles_have_an_empty_diff(self):
        code, out = run_cli("profile", "diff", STAND, STAND, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["diff"], {})


class ProfileCoverageTests(unittest.TestCase):
    def _rows(self, *extra) -> dict:
        code, out = run_cli("profile", "coverage", "--profile", STAND, "--json", *extra)
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        return {row["scenario_id"]: row for row in payload["coverage"]}, payload

    def test_available_kinds_come_from_evidence_and_memory(self):
        _, payload = self._rows()
        self.assertEqual(sorted(payload["available_kinds"]),
                         ["memory_snapshot", "tool_calls"])

    def test_scenario_with_its_sources_present_can_reach_state(self):
        rows, _ = self._rows()
        self.assertEqual(rows["poison-to-tool-chain"]["reachable"], "state")
        # The memory predicate is an optional amplifier; the foreign tool call
        # is the primary proof and therefore the only capability gate.
        self.assertEqual(sorted(rows["poison-to-tool-chain"]["required_kinds"]),
                         ["tool_calls"])
        self.assertEqual(rows["poison-to-tool-chain"]["missing_kinds"], [])

    def test_text_only_scenario_is_capped_at_indirect(self):
        rows, _ = self._rows()
        self.assertEqual(rows["system-prompt-leak"]["reachable"], "text")
        self.assertEqual(rows["system-prompt-leak"]["required_kinds"], [])

    def test_missing_source_makes_a_scenario_unobservable(self):
        code, out = run_cli("profile", "coverage", "--profile", DVAA,
                            "--scenario", "poison-to-tool-chain", "--json")
        self.assertEqual(code, 0, out)
        row = json.loads(out)["coverage"][0]
        self.assertEqual(row["reachable"], "unobservable")
        self.assertIn("tool_calls", row["missing_kinds"])

    def test_memory_goal_still_needs_an_action_source(self):
        """US-04 AC2: память — усилитель; без источника вызовов state недостижим."""
        code, out = run_cli("profile", "coverage", "--profile", DVAA,
                            "--scenario", "mem-policy-conformant", "--json")
        self.assertEqual(code, 0, out)
        row = json.loads(out)["coverage"][0]
        self.assertEqual(row["reachable"], "unobservable")
        self.assertEqual(row["missing_kinds"], ["tool_calls"])

    def test_trace_provider_counts_as_a_tool_call_source(self):
        import tempfile
        from pathlib import Path
        source = Path(DVAA).read_text(encoding="utf-8").replace(
            "  - id: canary\n    provider: http-canary\n    config: {bind: \"127.0.0.1:0\"}",
            "  - id: calls\n    provider: trace\n    config: {backend: otel, path: spans.jsonl}",
        )
        path = Path(tempfile.mkdtemp()) / "traced.yaml"
        path.write_text(source, encoding="utf-8")
        code, out = run_cli("profile", "coverage", "--profile", str(path),
                            "--scenario", "poison-to-tool-chain", "--json")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertIn("tool_calls", payload["available_kinds"])
        self.assertEqual(payload["coverage"][0]["reachable"], "state")

    def test_human_output_flags_what_is_missing(self):
        code, out = run_cli("profile", "coverage", "--profile", DVAA,
                            "--scenario", "poison-to-tool-chain")
        self.assertEqual(code, 0)
        self.assertIn("tool_calls", out)


if __name__ == "__main__":
    unittest.main()
