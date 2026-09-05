import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock

from agentic_redteam.adapters.identities.docker_exec_mint import DockerExecMintProvider
from agentic_redteam.profile.schema import TargetProfile
from tests.fakes import FakeRunner


class MintIdentityTests(unittest.TestCase):
    def setUp(self):
        self.config = TargetProfile.load(Path(__file__).with_name("data") / "profile_stand.yaml").identities

    def test_mint_uses_profile_role_and_compose_service(self):
        runner = Mock(wraps=FakeRunner(["diagnostic\nsk-genai-abc\n"]))
        credential = DockerExecMintProvider(self.config, runner).acquire("attacker")
        self.assertEqual(credential.headers["Authorization"], "Bearer sk-genai-abc")
        self.assertEqual(credential.principal.value, "1001")
        args, kwargs = runner.call_args
        self.assertEqual(args[0], ["docker", "compose", "-f", "stand/docker-compose.yml", "exec", "-T", "agent-api", "python", "-"])
        self.assertIn("generate_key('1001'", kwargs["input"])
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 30)

    def test_invalid_empty_and_failing_output_does_not_disclose_credentials(self):
        for output in ("", "private-invalid-key\n"):
            with self.subTest(output=output), self.assertRaises(RuntimeError) as caught:
                DockerExecMintProvider(self.config, FakeRunner([output])).acquire("attacker")
            self.assertNotIn("private-invalid-key", str(caught.exception))
        runner = Mock(side_effect=subprocess.CalledProcessError(1, ["docker"], output="private-key"))
        with self.assertRaises(RuntimeError) as caught:
            DockerExecMintProvider(self.config, runner).acquire("attacker")
        self.assertNotIn("private-key", str(caught.exception))
