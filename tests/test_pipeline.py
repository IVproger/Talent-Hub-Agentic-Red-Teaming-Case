from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import UTC, datetime
from pathlib import Path

from agentic_redteam.llm import LLMRoleConfig, LLMRequestError, default_role_configs
from agentic_redteam.pipeline import (
    PipelineConfigurationError,
    PipelineDependencies,
    RunConfig,
    generate_report,
    redact_secrets,
    run_pipeline,
)
from agentic_redteam.state import MemorySnapshot, ScenarioTrace, StepTrace, ToolCall


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.response


class FakeTracer:
    def log_marker(self):
        return 0

    def tool_calls_since(self, marker):
        return [ToolCall(tool="client_data_access", cus="1002")]


class FakeTargetClient:
    def chat(self, content, session_id, auth_mode="vulnerable"):
        return "target response"


class FailingTargetClient:
    def chat(self, content, session_id, auth_mode="vulnerable"):
        raise RuntimeError(
            "target unavailable " + os.environ.get("SERVICE_API_KEY", "")
        )


class FakeTargetRuntime:
    def __init__(self):
        self.calls = []

    def assert_matches(self, selected):
        self.calls.append(selected)


class FakeSpan:
    def __init__(self, observation_id):
        self.id = observation_id

    def update(self, **_values):
        return None


class FakeTelemetry:
    trace_id = "trace-run-test"
    trace_url = "http://localhost:3001/project/agentic-redteam/traces/trace-run-test"
    root_observation_id = "root-observation"
    warning = None

    @contextmanager
    def run(self, *_args, **_kwargs):
        yield FakeSpan(self.root_observation_id)

    @contextmanager
    def observation(self, name, **_kwargs):
        yield FakeSpan("attempt-observation" if name.startswith("attempt.") else name)

    def score_attempt(self, *_args):
        return None

    def score_run(self, *_args):
        return None

    def flush(self):
        return None


class FakeScenarioRunner:
    def __init__(self):
        self.calls = []
        self.last_trace = None

    def run(self, scenario, on_step=None):
        self.calls.append(scenario)
        target_cus = str(scenario.params["target_cus"])
        step = StepTrace(
            name="activate",
            actor_cus=str(scenario.roles["attacker"]["cus"]),
            request=scenario.render(scenario.steps[0]["message"]),
            response="synthetic target response",
            tool_calls=[ToolCall(tool="client_data_access", cus=target_cus)],
            memory_before=MemorySnapshot(),
            memory_after=MemorySnapshot(),
        )
        trace = ScenarioTrace(
            scenario_id=scenario.id,
            steps=[step],
            scores={
                "success": True,
                "assertions": [
                    {
                        "type": "tool_cus_mismatch",
                        "passed": True,
                        "detail": f"tool accessed cus={target_cus}",
                    }
                ],
            },
        )
        self.last_trace = trace
        if on_step:
            on_step(step, 1, 1)
        return trace


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.arch = root / "arch.mmd"
        self.card = root / "card.md"
        self.target = root / "target.yaml"
        self.arch.write_text("flowchart LR; A-->B", encoding="utf-8")
        self.card.write_text("target", encoding="utf-8")
        self.target.write_text(
            """target:\n  auth_mode: vulnerable\nidentities:\n  roles:\n    attacker: {cus: '1001'}\n    victim: {cus: '1002'}\nattack:\n  num_candidates: 1\n""",
            encoding="utf-8",
        )
        self.runs = root / "runs"

    def tearDown(self):
        self.temp.cleanup()

    def config(self, **changes):
        values = dict(
            target_config=self.target,
            arch=self.arch,
            system_card=self.card,
            output_root=self.runs,
            llm_roles=default_role_configs(),
        )
        values.update(changes)
        return RunConfig(**values)

    def dependencies(self):
        return PipelineDependencies(
            generator=FakeLLM('["payload"]'),
            reporter=FakeLLM("# Report"),
            tracer=FakeTracer(),
            target_client=FakeTargetClient(),
            target_runtime=FakeTargetRuntime(),
            id_factory=lambda: "run-test",
            now=lambda: datetime(2026, 9, 3, tzinfo=UTC),
        )

    def test_full_fake_run_is_state_based_and_consistent(self):
        events = []
        result = run_pipeline(self.config(), events.append, self.dependencies())
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.asr_percent, 100)
        self.assertEqual(result.attempts[0].verdict, "proven")
        self.assertIn("attempt_completed", [event.stage for event in events])
        run_dir = Path(result.run_dir)
        status = json.loads((run_dir / "status.json").read_text())
        findings = json.loads((run_dir / "findings.json").read_text())
        config = json.loads((run_dir / "config.json").read_text())
        self.assertEqual(status["status"], "completed")
        self.assertEqual(findings["status"], "completed")
        self.assertEqual({status["run_id"], findings["run_id"], config["run_id"]}, {"run-test"})
        report = (run_dir / "report.md").read_text(encoding="utf-8")
        knowledge = (run_dir / "knowledge.jsonl").read_text(encoding="utf-8")
        self.assertIn("run-test", report)
        self.assertIn('"run_id": "run-test"', knowledge)

    def test_trace_and_attempt_ids_are_persisted_in_manifest(self):
        deps = self.dependencies()
        deps.telemetry = FakeTelemetry()
        result = run_pipeline(self.config(), dependencies=deps)
        manifest = json.loads(
            (Path(result.run_dir) / "observability.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["langfuse_trace_id"], "trace-run-test")
        self.assertEqual(manifest["root_observation_id"], "root-observation")
        self.assertEqual(
            manifest["attempt_observation_ids"], {"1": "attempt-observation"}
        )

    def test_bundled_scenario_runs_through_shared_pipeline_and_artifacts(self):
        deps = self.dependencies()
        deps.scenario_runner = FakeScenarioRunner()
        events = []

        result = run_pipeline(
            self.config(
                scenario_id="bac-tool-argument",
                victim_cus="2002",
                num_candidates=2,
            ),
            events.append,
            deps,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.scenario_id, "bac-tool-argument")
        self.assertEqual(result.asr_percent, 100)
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(deps.generator.prompts, [])
        self.assertEqual(len(deps.scenario_runner.calls), 2)
        self.assertTrue(all(item.verdict == "proven" for item in result.attempts))
        self.assertEqual(result.attempts[0].leaked_cus, ["2002"])
        self.assertEqual(result.attempts[0].steps[0]["name"], "activate")
        self.assertIn("scenario_step", [event.stage for event in events])

        run_dir = Path(result.run_dir)
        findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(findings["scenario_id"], "bac-tool-argument")
        self.assertEqual(config["scenario_id"], "bac-tool-argument")
        self.assertIn('"scenario_id": "bac-tool-argument"', (run_dir / "knowledge.jsonl").read_text(encoding="utf-8"))

    def test_zero_candidates_fails_before_writes(self):
        with self.assertRaises(PipelineConfigurationError):
            run_pipeline(self.config(num_candidates=0), dependencies=self.dependencies())
        self.assertFalse(self.runs.exists())

    def test_distinct_identity_is_required(self):
        with self.assertRaises(PipelineConfigurationError):
            run_pipeline(
                self.config(attacker_cus="1001", victim_cus="1001"),
                dependencies=self.dependencies(),
            )

    def test_cus_is_validated_before_generator_call(self):
        deps = self.dependencies()
        for value in ("", "   ", "cus-1001"):
            with self.subTest(value=value), self.assertRaises(PipelineConfigurationError):
                run_pipeline(
                    self.config(attacker_cus=value, victim_cus="1002"),
                    dependencies=deps,
                )
        self.assertEqual(deps.generator.prompts, [])

    def test_failed_attempt_is_unscored_and_persisted(self):
        deps = self.dependencies()
        deps.target_client = FailingTargetClient()
        with self.assertRaises(Exception) as raised:
            run_pipeline(self.config(), dependencies=deps)
        result = raised.exception.result
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.attempts[0].verdict, "error")
        self.assertEqual(result.asr_percent, 0)
        findings = json.loads(
            (Path(result.run_dir) / "findings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(findings["attempts_scored"], 0)
        report = (Path(result.run_dir) / "report.md").read_text(encoding="utf-8")
        self.assertIn("Incomplete security run", report)
        self.assertIn("run-test", report)

    def test_provider_failure_keeps_provider_error_type_and_partial_run(self):
        deps = self.dependencies()
        deps.generator = FakeLLM(None)

        def fail(_prompt):
            raise LLMRequestError("rate limit")

        deps.generator.complete = fail
        with self.assertRaises(LLMRequestError):
            run_pipeline(self.config(), dependencies=deps)
        run_dir = self.runs / "run-test"
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "failed")

    def test_mixed_role_configuration_reaches_the_correct_stages(self):
        roles = default_role_configs()
        roles["attack_generator"] = roles["attack_generator"].__class__(
            provider="openrouter", model="openai/attack"
        )
        target_model = LLMRoleConfig(
            provider="ollama", model="target-model"
        )
        roles["report_writer"] = roles["report_writer"].__class__(
            provider="openrouter", model="openai/report"
        )
        created = []

        def factory(config):
            created.append(config.model)
            return FakeLLM('["payload"]' if config.model == "openai/attack" else "# Report")

        deps = self.dependencies()
        deps.generator = None
        deps.reporter = None
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sentinel"}), patch(
            "agentic_redteam.pipeline.make_llm_client", side_effect=factory
        ):
            run_pipeline(self.config(llm_roles=roles, target_model=target_model), dependencies=deps)
        self.assertEqual(created, ["openai/attack", "openai/report"])
        self.assertEqual(deps.target_runtime.calls[0].model, "target-model")

    def test_secret_is_redacted_from_failed_run_artifacts(self):
        deps = self.dependencies()
        deps.target_client = FailingTargetClient()
        secret = "sk-SUPER-SECRET-SENTINEL"
        with patch.dict("os.environ", {"SERVICE_API_KEY": secret}):
            with self.assertRaises(Exception) as raised:
                run_pipeline(self.config(), dependencies=deps)
        contents = "".join(
            path.read_text(encoding="utf-8")
            for path in Path(raised.exception.result.run_dir).iterdir()
            if path.is_file()
        )
        self.assertNotIn(secret, contents)

    def test_target_response_is_complete_and_redacted_in_artifacts(self):
        secret = "sk-SUPER-SECRET-SENTINEL"
        deps = self.dependencies()
        deps.target_client = FakeTargetClient()
        deps.target_client.chat = lambda *_args, **_kwargs: "x" * 2500 + " " + secret
        result = run_pipeline(self.config(), dependencies=deps)
        self.assertEqual(len(result.attempts[0].response), 2501 + len("[redacted]"))
        contents = "".join(
            path.read_text(encoding="utf-8")
            for path in Path(result.run_dir).iterdir()
            if path.is_file()
        )
        self.assertNotIn(secret, contents)

    def test_target_endpoint_must_not_embed_credentials(self):
        self.target.write_text(
            """target:
  endpoint: https://secret@example.test
identities:
  roles:
    attacker: {cus: '1001'}
    victim: {cus: '1002'}
attack:
  num_candidates: 1
""",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(PipelineConfigurationError, "must not contain credentials"):
            run_pipeline(self.config(), dependencies=self.dependencies())

    def test_target_endpoint_rejects_query_and_malformed_url(self):
        for endpoint in (
            "https://example.test?api_key=secret",
            "https://example.test#secret",
            "http://[broken",
        ):
            with self.subTest(endpoint=endpoint):
                self.target.write_text(
                    f"""target:
  endpoint: {endpoint}
identities:
  roles:
    attacker: {{cus: '1001'}}
    victim: {{cus: '1002'}}
attack:
  num_candidates: 1
""",
                    encoding="utf-8",
                )
                with self.assertRaises(PipelineConfigurationError):
                    run_pipeline(self.config(), dependencies=self.dependencies())

    def test_target_temperature_is_rejected_instead_of_ignored(self):
        roles = default_role_configs()
        target_model = LLMRoleConfig(temperature=0.5)
        with self.assertRaisesRegex(PipelineConfigurationError, "temperature"):
            run_pipeline(self.config(llm_roles=roles, target_model=target_model), dependencies=self.dependencies())

    def test_redactor_preserves_words_and_removes_authorization_values(self):
        text = (
            'risk-based and task-specific; '
            '"Authorization": "Basic Zm9vOmJhcg=="; '
            "Authorization: ApiKey abc123\n"
            "Bearer eyJhbGciOiJIUzI1NiJ9.secret.signature "
            "sk-1234567890abcdef sk-abcdefghijklmnop"
        )
        redacted = redact_secrets(text)
        self.assertIn("risk-based", redacted)
        self.assertIn("task-specific", redacted)
        for secret in (
            "Zm9vOmJhcg==",
            "abc123",
            "eyJhbGci",
            "sk-1234567890abcdef",
            "sk-abcdefghijklmnop",
        ):
            self.assertNotIn(secret, redacted)

    def test_report_prompt_is_bounded_but_knowledge_response_stays_complete(self):
        reporter = FakeLLM("# Report")
        attempts = [
            self._attempt(index, "x" * 10_000)
            for index in range(100)
        ]
        for attempt in attempts:
            attempt.steps = [
                {
                    "name": "activate",
                    "actor_cus": "1001",
                    "request": "q" * 10_000,
                    "response": "r" * 10_000,
                    "tool_calls": [],
                    "new_global_policies": ["p" * 10_000],
                    "finalize_facts": [{"statement": "f" * 10_000}],
                    "memory_before": {},
                    "memory_after": {"agent_policy_memories": 1},
                }
            ]
            attempt.assertions = [
                {"type": "response_contains", "passed": True, "detail": "d" * 10_000}
            ]
        generate_report(reporter, "run", attempts, 0, "1001", "1002")
        self.assertLess(len(reporter.prompts[0]), 100_000)
        self.assertIn("full value is stored in knowledge.jsonl", reporter.prompts[0])
        self.assertEqual(len(attempts[0].response), 10_000)

    @staticmethod
    def _attempt(index, response):
        from agentic_redteam.pipeline import AttemptResult

        return AttemptResult(
            run_id="run",
            attempt=index,
            actor_cus="1001",
            victim_cus="1002",
            payload="payload " + "y" * 2_000,
            response=response,
            tool_calls=[],
            leaked_cus=[],
            verdict="not_proven",
            compromise_point=None,
        )


if __name__ == "__main__":
    unittest.main()
