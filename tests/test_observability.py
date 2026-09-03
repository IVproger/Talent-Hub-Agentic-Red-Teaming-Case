from __future__ import annotations

import unittest
from contextlib import contextmanager

from agentic_redteam.observability import (
    LangfuseConfig,
    LangfuseTelemetry,
    ObservabilityConfigurationError,
    langfuse_config_from_mapping,
    sanitize_trace_value,
)


class FakeObservation:
    trace_id = "a" * 32
    id = "b" * 16

    def __init__(self):
        self.values = []

    def update(self, **values):
        self.values.append(values)


class FakeClient:
    def __init__(self):
        self.started = []
        self.scores = []
        self.flushed = False

    def create_trace_id(self, seed=None):
        self.seed = seed
        return "a" * 32

    @contextmanager
    def start_as_current_observation(self, **values):
        self.started.append(values)
        yield FakeObservation()

    def create_score(self, **values):
        self.scores.append(values)

    def flush(self):
        self.flushed = True


class ObservabilityTests(unittest.TestCase):
    def test_disabled_config_requires_no_credentials(self):
        telemetry = LangfuseTelemetry(LangfuseConfig(), environ={})
        self.assertFalse(telemetry.active)
        self.assertIsNone(telemetry.warning)

    def test_enabled_missing_credentials_is_fail_open(self):
        telemetry = LangfuseTelemetry(LangfuseConfig(enabled=True), environ={})
        self.assertFalse(telemetry.active)
        self.assertIn("credentials", telemetry.warning)

    def test_trace_metadata_scores_and_url_are_correlated(self):
        client = FakeClient()
        config = LangfuseConfig(enabled=True, project_id="project-id")
        telemetry = LangfuseTelemetry(
            config,
            environ={
                "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
                "LANGFUSE_SECRET_KEY": "sk-lf-test",
            },
            client=client,
        )
        with telemetry.run("run-1", metadata={"scenario_id": "bac"}):
            with telemetry.observation("attempt.1") as attempt:
                observation_id = attempt.id
            telemetry.score_attempt(observation_id, "proven")
        telemetry.score_run(100)
        telemetry.flush()
        self.assertEqual(client.seed, "run-1")
        self.assertEqual(telemetry.trace_id, "a" * 32)
        self.assertIn("/project/project-id/traces/", telemetry.trace_url)
        self.assertEqual([item["name"] for item in client.scores], [
            "verdict", "attack_success", "asr_percent"
        ])
        self.assertTrue(client.flushed)

    def test_redaction_is_recursive_and_bounded(self):
        value = sanitize_trace_value(
            {
                "Authorization": "Bearer secret",
                "nested": {"api_key": "secret", "text": "sk-secretvalue " + "x" * 50},
            },
            max_chars=20,
        )
        self.assertEqual(value["Authorization"], "[redacted]")
        self.assertEqual(value["nested"]["api_key"], "[redacted]")
        self.assertNotIn("sk-secretvalue", value["nested"]["text"])
        self.assertIn("truncated", value["nested"]["text"])

    def test_invalid_host_and_unknown_fields_are_rejected(self):
        with self.assertRaises(ObservabilityConfigurationError):
            langfuse_config_from_mapping({"langfuse": {"host": "http://user:pass@host"}})
        with self.assertRaises(ObservabilityConfigurationError):
            langfuse_config_from_mapping({"langfuse": {"unknown": True}})


if __name__ == "__main__":
    unittest.main()
