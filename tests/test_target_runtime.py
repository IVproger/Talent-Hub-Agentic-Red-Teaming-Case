from __future__ import annotations

import json
import subprocess
import unittest

from agentic_redteam.llm import LLMRoleConfig
from agentic_redteam.target_runtime import (
    TargetConfigurationError,
    TargetRuntime,
    expected_target_settings,
)


class TargetRuntimeTests(unittest.TestCase):
    def runner_for(self, **values):
        payload = {
            "base_url": "http://host.docker.internal:11434/v1",
            "research_model": "openai:qwen3:8b",
            "summarization_model": "openai:qwen3:8b",
            "has_api_key": True,
            "credential_valid": True,
            "model_available": True,
            **values,
        }

        def runner(command, **kwargs):
            self.assertEqual(kwargs["timeout"], 10)
            compile(command[-1], "<target-readiness-probe>", "exec")
            self.assertIn("/models", command[-1])
            self.assertIn("/key", command[-1])
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        return runner

    def test_matching_ollama_target(self):
        state = TargetRuntime("compose.yml", self.runner_for()).assert_matches(
            LLMRoleConfig()
        )
        self.assertEqual(state.research_model, "openai:qwen3:8b")

    def test_both_live_models_must_match(self):
        runtime = TargetRuntime(
            "compose.yml", self.runner_for(summarization_model="openai:other")
        )
        with self.assertRaisesRegex(TargetConfigurationError, "SUMMARIZATION_MODEL"):
            runtime.assert_matches(LLMRoleConfig())

    def test_openrouter_key_is_checked_inside_target(self):
        runtime = TargetRuntime(
            "compose.yml",
            self.runner_for(
                base_url="https://openrouter.ai/api/v1",
                research_model="openai:openai/test",
                summarization_model="openai:openai/test",
                has_api_key=False,
            ),
        )
        with self.assertRaises(TargetConfigurationError):
            runtime.assert_matches(
                LLMRoleConfig(provider="openrouter", model="openai/test")
            )

    def test_matching_openrouter_target(self):
        runtime = TargetRuntime(
            "compose.yml",
            self.runner_for(
                base_url="https://openrouter.ai/api/v1",
                research_model="openai:openai/test",
                summarization_model="openai:openai/test",
            ),
        )
        state = runtime.assert_matches(
            LLMRoleConfig(provider="openrouter", model="openai/test")
        )
        self.assertTrue(state.has_api_key)

    def test_ollama_target_requires_placeholder_key(self):
        runtime = TargetRuntime("compose.yml", self.runner_for(has_api_key=False))
        with self.assertRaises(TargetConfigurationError):
            runtime.assert_matches(LLMRoleConfig())

    def test_ollama_target_url_is_normalized_for_docker(self):
        url, model = expected_target_settings(
            LLMRoleConfig(base_url="http://localhost:11434/api/chat")
        )
        self.assertEqual(url, "http://host.docker.internal:11434/v1")
        self.assertEqual(model, "openai:qwen3:8b")

    def test_base_url_mismatch_is_rejected(self):
        runtime = TargetRuntime(
            "compose.yml", self.runner_for(base_url="http://wrong:11434/v1")
        )
        with self.assertRaises(TargetConfigurationError):
            runtime.assert_matches(LLMRoleConfig())

    def test_unavailable_target_model_is_rejected(self):
        runtime = TargetRuntime(
            "compose.yml", self.runner_for(model_available=False)
        )
        with self.assertRaisesRegex(TargetConfigurationError, "model available=no"):
            runtime.assert_matches(LLMRoleConfig())

    def test_target_temperature_is_rejected_before_inspection(self):
        called = []

        def runner(*args, **kwargs):
            called.append((args, kwargs))

        with self.assertRaisesRegex(TargetConfigurationError, "temperature"):
            TargetRuntime("explicit-compose.yml", runner).assert_matches(
                LLMRoleConfig(temperature=0.1)
            )
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
