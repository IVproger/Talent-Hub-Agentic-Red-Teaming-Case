from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from agentic_redteam.doctor import _probe_provider, run_checks
from agentic_redteam.llm import LLMRoleConfig, role_configs_from_mapping


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class DoctorTests(unittest.TestCase):
    def test_regular_stand_directory_is_accepted_without_git_metadata(self):
        roles = role_configs_from_mapping(None)
        with tempfile.TemporaryDirectory() as temporary:
            stand = Path(temporary) / "stand"
            (stand / "app").mkdir(parents=True)
            (stand / "docker-compose.yml").write_text(
                "services: {}\n", encoding="utf-8"
            )
            (stand / "app" / "api_server.py").write_text("", encoding="utf-8")
            checks = run_checks(
                roles,
                target_api="http://localhost:8600",
                compose_file=str(stand / "docker-compose.yml"),
                check_network=False,
            )
        stand_check = next(item for item in checks if item.name == "stand")
        self.assertTrue(stand_check.ok)
        self.assertIn("исходниками стенда", stand_check.message)

    def test_ollama_probe_checks_selected_model(self):
        response = FakeResponse({"models": [{"name": "qwen3:8b"}]})
        with patch("urllib.request.urlopen", return_value=response):
            ok, _ = _probe_provider(LLMRoleConfig(model="missing:latest"))
        self.assertFalse(ok)

    def test_openrouter_probe_sends_key_and_checks_model(self):
        response = FakeResponse({"data": [{"id": "openai/test"}]})
        config = LLMRoleConfig(provider="openrouter", model="openai/test")
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sentinel"}), patch(
            "urllib.request.urlopen", return_value=response
        ) as opened:
            ok, _ = _probe_provider(config)
        self.assertTrue(ok)
        self.assertEqual(opened.call_count, 2)
        for call in opened.call_args_list:
            self.assertEqual(
                call.args[0].get_header("Authorization"), "Bearer sentinel"
            )
        self.assertTrue(opened.call_args_list[0].args[0].full_url.endswith("/key"))

    def test_openrouter_probe_rejects_invalid_key_before_public_models(self):
        config = LLMRoleConfig(provider="openrouter", model="openai/test")
        error = HTTPError(
            "https://openrouter.ai/api/v1/key",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"invalid key"}'),
        )
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "invalid"}), patch(
            "urllib.request.urlopen", side_effect=error
        ) as opened:
            ok, message = _probe_provider(config)
        self.assertFalse(ok)
        self.assertIn("учётные данные", message)
        self.assertEqual(opened.call_count, 1)

    def test_target_provider_is_not_probed_from_host(self):
        calls = []
        roles = role_configs_from_mapping(None)
        with tempfile.TemporaryDirectory() as temporary:
            checks = run_checks(
                roles,
                target_api="http://localhost:8600",
                compose_file=str(Path(temporary) / "missing.yml"),
                check_network=False,
                target_model=LLMRoleConfig(provider="openrouter", model="openai/test"),
                provider_probe=lambda config: calls.append(config) or (True, "ok"),
            )
        self.assertEqual(calls, [])
        self.assertTrue(any(item.name == "llm_config" and item.ok for item in checks))

    def test_malformed_target_url_becomes_failed_check(self):
        roles = role_configs_from_mapping(None)
        with tempfile.TemporaryDirectory() as temporary:
            with patch("shutil.which", return_value=None):
                checks = run_checks(
                    roles,
                    target_api="http://[broken",
                    compose_file=str(Path(temporary) / "missing.yml"),
                    provider_probe=lambda _config: (True, "ok"),
                    target_runtime=SimpleNamespace(
                        assert_matches=lambda _config: SimpleNamespace(
                            research_model="qwen3:8b", base_url="http://ollama"
                        )
                    ),
                )
        agent_check = next(item for item in checks if item.name == "agent_api")
        self.assertFalse(agent_check.ok)


if __name__ == "__main__":
    unittest.main()
