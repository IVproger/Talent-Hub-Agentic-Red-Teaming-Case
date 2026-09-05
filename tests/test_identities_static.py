import copy
import unittest
from pathlib import Path

from agentic_redteam.adapters.identities.base import IdentityProvider
from agentic_redteam.adapters.identities.static import StaticIdentityProvider
from agentic_redteam.errors import PipelineConfigurationError
from agentic_redteam.profile.schema import TargetProfile


class StaticIdentityTests(unittest.TestCase):
    def setUp(self):
        self.config = TargetProfile.load(Path(__file__).with_name("data") / "profile_dvaa.yaml").identities

    def test_role_principal_and_body_fields(self):
        provider = StaticIdentityProvider(self.config)
        self.assertIsInstance(provider, IdentityProvider)
        credential = provider.acquire("attacker")
        self.assertEqual(credential.principal.attribute, "agent_id")
        self.assertEqual(credential.principal.value, "evil-agent")
        self.assertEqual(credential.body_fields, {"from": "evil-agent"})
        credential.body_fields["from"] = "changed"
        self.assertEqual(provider.acquire("attacker").body_fields["from"], "evil-agent")
        provider.release(credential)

    def test_secrets_are_read_from_environment_only_when_acquiring(self):
        config = copy.deepcopy(self.config)
        config["credential"].update(secret_env="TARGET_KEY", headers={"Authorization": "Bearer {secret}"})
        env = {}
        provider = StaticIdentityProvider(config, environ=env)
        with self.assertRaises(PipelineConfigurationError):
            provider.acquire("attacker")
        env["TARGET_KEY"] = "private-value"
        credential = provider.acquire("attacker")
        self.assertEqual(credential.headers["Authorization"], "Bearer private-value")
        self.assertNotIn("private-value", repr(credential))

    def test_bad_roles_and_unresolved_templates_fail_explicitly(self):
        with self.assertRaises(PipelineConfigurationError):
            StaticIdentityProvider(self.config).acquire("unknown")
        config = copy.deepcopy(self.config)
        config["credential"]["body_fields"]["from"] = "{missing}"
        with self.assertRaises(PipelineConfigurationError):
            StaticIdentityProvider(config).acquire("attacker")

    def test_decimal_principal_is_validated_without_losing_leading_zeroes(self):
        config = {"principal": {"attribute": "user", "type": "decimal"},
                  "roles": {"actor": {"user": "001"}}, "credential": {}}
        self.assertEqual(StaticIdentityProvider(config).acquire("actor").principal.value, "001")
        config["roles"]["actor"]["user"] = "bad"
        with self.assertRaises(PipelineConfigurationError):
            StaticIdentityProvider(config).acquire("actor")
