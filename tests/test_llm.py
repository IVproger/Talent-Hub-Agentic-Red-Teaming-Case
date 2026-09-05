from __future__ import annotations

import json
import unittest

from agentic_redteam.llm import (
    LLMConfigurationError,
    LLMRoleConfig,
    apply_role_overrides,
    make_llm_client,
    role_configs_from_mapping,
    validate_role_configs,
)


class LLMConfigurationTests(unittest.TestCase):
    def test_provider_change_resets_provider_specific_defaults(self):
        roles = role_configs_from_mapping(
            {"attack_generator": {"provider": "openrouter", "model": "openai/test"}}
        )
        self.assertEqual(roles["attack_generator"].base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(roles["attack_generator"].api_key_env, "OPENROUTER_API_KEY")

        back = apply_role_overrides(
            roles,
            {"attack_generator": {"provider": "ollama", "model": "qwen3:8b"}},
        )
        self.assertEqual(back["attack_generator"].base_url, "http://localhost:11434")
        self.assertIsNone(back["attack_generator"].api_key_env)

    def test_openrouter_requires_key_before_transport(self):
        called = []
        with self.assertRaises(LLMConfigurationError):
            make_llm_client(
                LLMRoleConfig(provider="openrouter", model="openai/test"),
                environ={},
                transport=lambda *_: called.append(True),
            )
        self.assertEqual(called, [])

    def test_engine_roles_include_analyst_without_target(self):
        roles = role_configs_from_mapping(
            {"analyst": {"provider": "openrouter", "model": "openai/test"}}
        )
        self.assertEqual(set(roles), {"attack_generator", "report_writer", "analyst"})
        validate_role_configs(roles, environ={})
        with self.assertRaises(LLMConfigurationError):
            validate_role_configs(roles, environ={}, credential_roles=("analyst",))

    def test_target_is_not_an_engine_role(self):
        with self.assertRaises(LLMConfigurationError):
            role_configs_from_mapping({"target_agent": {"model": "target"}})

    def test_null_model_has_a_field_level_configuration_error(self):
        with self.assertRaisesRegex(LLMConfigurationError, "model must be a string"):
            role_configs_from_mapping({"report_writer": {"model": None}})

    def test_credentials_are_rejected_in_provider_url(self):
        with self.assertRaisesRegex(LLMConfigurationError, "must not contain credentials"):
            LLMRoleConfig(base_url="https://secret@example.test").validate()

    def test_query_fragment_and_malformed_provider_urls_are_rejected(self):
        for url in (
            "https://openrouter.ai/api/v1?api_key=secret",
            "https://openrouter.ai/api/v1#secret",
            "http://[broken",
            "http://example.test:not-a-port",
        ):
            with self.subTest(url=url), self.assertRaises(LLMConfigurationError):
                LLMRoleConfig(base_url=url).validate()

    def test_ollama_and_openrouter_use_distinct_contracts(self):
        requests = []

        def transport(request, timeout):
            requests.append((request, timeout, json.loads(request.data)))
            if "openrouter" in request.full_url:
                return {"choices": [{"message": {"content": "openrouter"}}]}
            return {"message": {"content": "ollama"}}

        ollama = make_llm_client(LLMRoleConfig(), environ={}, transport=transport)
        router = make_llm_client(
            LLMRoleConfig(provider="openrouter", model="openai/test"),
            environ={"OPENROUTER_API_KEY": "sk-test-SENTINEL"},
            transport=transport,
        )
        self.assertEqual(ollama.complete("hello"), "ollama")
        self.assertEqual(router.complete("hello"), "openrouter")
        self.assertTrue(requests[0][0].full_url.endswith("/api/chat"))
        self.assertTrue(requests[1][0].full_url.endswith("/chat/completions"))
        self.assertEqual(requests[1][0].get_header("Authorization"), "Bearer sk-test-SENTINEL")
        self.assertNotIn("sk-test-SENTINEL", str(router.config.safe_dict()))


if __name__ == "__main__":
    unittest.main()
