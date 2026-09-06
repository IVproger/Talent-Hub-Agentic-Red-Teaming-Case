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
    extract_json,
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
        self.assertEqual(set(roles), {"attack_generator", "report_writer", "analyst", "judge"})
        validate_role_configs(roles, environ={})
        with self.assertRaises(LLMConfigurationError):
            validate_role_configs(roles, environ={}, credential_roles=("analyst",))


    def test_judge_is_an_independent_role_defaulting_local(self):
        roles = role_configs_from_mapping(
            {"judge": {"provider": "ollama", "model": "qwen3:8b"}}
        )
        self.assertIn("judge", roles)
        self.assertEqual(roles["judge"].model, "qwen3:8b")
        # overriding judge alone does not touch analyst
        self.assertEqual(roles["analyst"].model, roles["attack_generator"].model)
        # judge needs no credentials on the local default
        validate_role_configs(roles, environ={})

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



class ExtractJsonTests(unittest.TestCase):
    def test_bare_object_and_array(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('[1, 2]'), [1, 2])

    def test_strips_markdown_fence(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('```\n[1]\n```'), [1])

    def test_ignores_surrounding_prose(self):
        self.assertEqual(extract_json('Вот результат:\n{"a": 1}\nготово'), {"a": 1})

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            extract_json('нет тут json')



class ProviderRoutingTests(unittest.TestCase):
    def _payload(self, **cfg_kwargs):
        payloads = []

        def transport(request, timeout):
            payloads.append(json.loads(request.data))
            return {"choices": [{"message": {"content": "ok"}}]}

        client = make_llm_client(
            LLMRoleConfig(provider="openrouter", model="z-ai/glm-5.3-flash",
                          **cfg_kwargs),
            environ={"OPENROUTER_API_KEY": "sk-test-SENTINEL"},
            transport=transport,
        )
        client.complete("hi")
        return payloads[0]

    def test_routing_is_sent_as_provider_block(self):
        routing = {"order": ["CoreWeave"], "allow_fallbacks": False}
        self.assertEqual(self._payload(routing=routing)["provider"], routing)

    def test_no_routing_means_no_provider_block(self):
        self.assertNotIn("provider", self._payload())

    def test_max_tokens_sent_when_set(self):
        self.assertEqual(self._payload(max_tokens=8000)["max_tokens"], 8000)

    def test_max_tokens_absent_when_unset(self):
        self.assertNotIn("max_tokens", self._payload())

    def test_reasoning_sent_when_set(self):
        self.assertEqual(
            self._payload(reasoning={"enabled": False})["reasoning"],
            {"enabled": False},
        )


if __name__ == "__main__":
    unittest.main()
