"""Наблюдаемость прогона: подключена, но на вердикт и артефакты не влияет."""
from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path

from agentic_redteam.campaign.orchestrator import PlannedScenario, run_campaign
from agentic_redteam.campaign.runner import RunnerDeps, ScenarioStep
from agentic_redteam.normalize.facts import Facts, ObservedToolCall
from agentic_redteam.storage.runs import RunStorage
from tests.fakes import FakeAdapter, FakeEvidenceSource


class Telemetry:
    """Стоит на месте LangfuseTelemetry: тот же публичный контракт."""

    def __init__(self, *, breaks=False):
        self.trace_id = "trace-1"
        self.trace_url = "http://localhost:3001/t/trace-1"
        self.root_observation_id = "obs-root"
        self.warning = None
        self.breaks = breaks
        self.flushed = False
        self.names: list[str] = []

    def observation(self, name, **_kw):
        self.names.append(name)
        return nullcontext()

    def flush(self) -> None:
        if self.breaks:
            raise RuntimeError("Langfuse недоступен")
        self.flushed = True


def scenario():
    return PlannedScenario(id="bac", attack_class="cls", standard_refs=["AML.T0012"],
                           actor="1001", payloads=["p"],
                           goal=[{"type": "tool_principal_mismatch"}], boundary="user",
                           steps=[ScenarioStep("activate", "attacker", payload=True)])


def deps(telemetry):
    return RunnerDeps(FakeAdapter({"attacker": "1001"}, ["ok"] * 8),
                      FakeEvidenceSource([Facts(tool_calls=[
                          ObservedToolCall("get_portfolio", "1002", {}, "raw")])] * 4),
                      telemetry=telemetry)


class TelemetryArtifactTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def _run(self, telemetry, run_id="r1"):
        return run_campaign([scenario()], deps(telemetry), storage=RunStorage(self.root),
                            run_id=run_id, modes=["vulnerable"])

    def test_manifest_links_the_run_to_its_trace(self):
        telemetry = Telemetry()
        self._run(telemetry)
        manifest = json.loads((self.root / "r1" / "observability.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["trace_id"], "trace-1")
        self.assertEqual(manifest["trace_url"], "http://localhost:3001/t/trace-1")
        self.assertEqual(manifest["root_observation_id"], "obs-root")
        self.assertTrue(telemetry.flushed)

    def test_run_without_telemetry_writes_no_manifest(self):
        findings = self._run(None, run_id="r2")
        self.assertEqual(findings["asr_percent"], 100.0)
        self.assertFalse((self.root / "r2" / "observability.json").exists())

    def test_broken_telemetry_never_costs_the_verdict(self):
        findings = self._run(Telemetry(breaks=True), run_id="r3")
        self.assertEqual(findings["asr_percent"], 100.0)
        self.assertTrue((self.root / "r3" / "findings.json").exists())
        self.assertTrue((self.root / "r3" / "report.md").exists())


class CliWiringTests(unittest.TestCase):
    def test_cli_builds_telemetry_from_the_configuration(self):
        from agentic_redteam.app_cli import telemetry_from_config
        telemetry = telemetry_from_config("config/target.yaml")
        self.assertIsNotNone(telemetry)
        self.assertTrue(hasattr(telemetry, "observation"))

    def test_unusable_configuration_yields_no_telemetry_not_a_crash(self):
        from agentic_redteam.app_cli import telemetry_from_config
        self.assertIsNone(telemetry_from_config("/definitely/missing.yaml"))


if __name__ == "__main__":
    unittest.main()
