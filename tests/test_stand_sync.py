from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest

import yaml
from pathlib import Path

from agentic_redteam.stand_sync import StandSyncError, _render_updated_env, sync_stand


class FakeRuntime:
    def __init__(self):
        self.selected = []

    def assert_matches(self, selected):
        self.selected.append(selected)


class StandSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.compose = self.root / "stand" / "docker-compose.yml"
        self.compose.parent.mkdir()
        self.compose.write_text("services: {}\n", encoding="utf-8")
        self.env_file = self.compose.parent / ".env"
        self.env_file.write_text(
            "# keep\nOPENAI_API_KEY=sk-secret\n"
            "OPENAI_BASE_URL=http://old/v1\n"
            "RESEARCH_MODEL=openai:old\n"
            "SUMMARIZATION_MODEL=openai:old\nMAX_REACT_TOOL_CALLS=2\n",
            encoding="utf-8",
        )
        self.config = self.root / "target.yaml"
        self.config.write_text(
            "target:\n  compose_file: stand/docker-compose.yml\n  profile: profile.yaml\n",
            encoding="utf-8",
        )
        profile = yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "profiles/genai-invest-stand/1.0.0.yaml").read_text()
        )
        profile["entrypoint"]["target_model"]["model"] = "z-ai/glm-5.3-flash"
        self.profile = self.root / "profile.yaml"
        self.profile.write_text(yaml.safe_dump(profile), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_dry_run_is_secret_free_and_does_not_write(self):
        before = self.env_file.read_bytes()
        result = sync_stand(self.config, dry_run=True)
        self.assertTrue(result.changed)
        self.assertFalse(result.recreated)
        self.assertEqual(before, self.env_file.read_bytes())
        rendered = str(result.to_dict())
        self.assertNotIn("sk-secret", rendered)
        self.assertEqual({item.key for item in result.changes}, {
            "OPENAI_BASE_URL", "RESEARCH_MODEL", "SUMMARIZATION_MODEL"
        })

    def test_model_comes_from_profile_even_when_engine_uses_another_provider(self):
        self.config.write_text(self.config.read_text() + "llm:\n  analyst: {provider: ollama, model: other}\n")
        result = sync_stand(self.config, dry_run=True)
        changes = {change.key: change.new for change in result.changes}
        self.assertEqual(changes["RESEARCH_MODEL"], "openai:z-ai/glm-5.3-flash")

    def test_missing_profile_reference_fails_before_writing(self):
        before = self.env_file.read_bytes()
        self.config.write_text("target:\n  compose_file: stand/docker-compose.yml\n")
        with self.assertRaisesRegex(StandSyncError, "target.profile"):
            sync_stand(self.config)
        self.assertEqual(self.env_file.read_bytes(), before)

    def test_missing_or_invalid_profile_fails_before_writing(self):
        before = self.env_file.read_bytes()
        for contents in (None, "[broken", "entrypoint: {}"):
            with self.subTest(contents=contents):
                if contents is None:
                    self.profile.unlink()
                else:
                    self.profile.write_text(contents)
                with self.assertRaises(StandSyncError):
                    sync_stand(self.config)
                self.assertEqual(self.env_file.read_bytes(), before)

    def test_invalid_target_model_does_not_fall_back_to_defaults(self):
        raw = yaml.safe_load(self.profile.read_text())
        for model in ({}, {"model": "example", "secret": "forbidden"}, {"model": None}):
            with self.subTest(model=model):
                raw["entrypoint"]["target_model"] = model
                self.profile.write_text(yaml.safe_dump(raw))
                with self.assertRaises(StandSyncError):
                    sync_stand(self.config, dry_run=True)

    def test_sync_preserves_secret_comments_permissions_and_is_idempotent(self):
        os.chmod(self.env_file, 0o640)
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, "", "")

        runtime = FakeRuntime()
        result = sync_stand(
            self.config, runner=runner, target_runtime=runtime
        )
        contents = self.env_file.read_text(encoding="utf-8")
        self.assertIn("# keep", contents)
        self.assertIn("OPENAI_API_KEY=sk-secret", contents)
        self.assertIn("RESEARCH_MODEL=openai:z-ai/glm-5.3-flash", contents)
        self.assertEqual(stat.S_IMODE(self.env_file.stat().st_mode), 0o640)
        self.assertTrue(result.recreated)
        self.assertEqual(
            calls[0][0][-4:], ["-d", "--no-deps", "--force-recreate", "agent-api"]
        )
        self.assertEqual(len(runtime.selected), 1)

        second = sync_stand(
            self.config, runner=runner, target_runtime=runtime
        )
        self.assertFalse(second.changed)
        self.assertTrue(second.verified)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(runtime.selected), 2)

    def test_duplicate_managed_setting_is_rejected_before_write(self):
        self.env_file.write_text(
            "OPENAI_BASE_URL=http://one\nOPENAI_BASE_URL=http://two\n",
            encoding="utf-8",
        )
        before = self.env_file.read_bytes()
        with self.assertRaisesRegex(StandSyncError, "more than once"):
            sync_stand(self.config, dry_run=True)
        self.assertEqual(before, self.env_file.read_bytes())

    def test_docker_failure_is_reported_without_exposing_secrets(self):
        def runner(command, **kwargs):
            raise subprocess.CalledProcessError(
                1, command, stderr="container failed with sk-secret"
            )

        with self.assertRaises(StandSyncError) as raised:
            sync_stand(self.config, runner=runner)
        self.assertNotIn("sk-secret", str(raised.exception))
        self.assertIn(
            "RESEARCH_MODEL=openai:z-ai/glm-5.3-flash",
            self.env_file.read_text(encoding="utf-8"),
        )

    def test_final_newline_style_is_preserved(self):
        rendered, _ = _render_updated_env(
            "OPENAI_BASE_URL=http://old\r\nRESEARCH_MODEL=old\r\nSUMMARIZATION_MODEL=old",
            {
                "OPENAI_BASE_URL": "http://new",
                "RESEARCH_MODEL": "openai:new",
                "SUMMARIZATION_MODEL": "openai:new",
            },
        )
        self.assertIn("\r\n", rendered)
        self.assertFalse(rendered.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
