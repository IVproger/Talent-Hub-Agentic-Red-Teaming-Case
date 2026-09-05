import unittest
from unittest.mock import Mock

from agentic_redteam.evidence.providers.state_reset import StateResetProvider
from tests.fakes import FakeRunner


class ResetTests(unittest.TestCase):
    def config(self):
        return {"compose_file": "stand/compose.yml",
                "mongo": {"service": "mongo", "db": "memory", "collections": ["facts"]},
                "redis": {"service": "redis", "key_patterns": ["working:*"]}}

    def test_reset_targets_only_declared_collections_and_keys(self):
        runner = Mock(wraps=FakeRunner(["", "working:1:s\nworking:2:s\n", "2\n"]))
        StateResetProvider(self.config(), runner).reset()
        calls = runner.call_args_list
        self.assertIn('"facts"', calls[0].kwargs["input"])
        self.assertIn("deleteMany", calls[0].kwargs["input"])
        self.assertIn("--scan", calls[1].args[0])
        self.assertIn("working:*", calls[1].args[0])
        self.assertEqual(calls[2].args[0][-3:], ["DEL", "working:1:s", "working:2:s"])
        self.assertNotIn("FLUSHALL", repr(calls))

    def test_calibrate_only_pings_and_never_resets(self):
        runner = Mock(wraps=FakeRunner(['{"ok":1}\n', "PONG\n"]))
        self.assertTrue(StateResetProvider(self.config(), runner).calibrate().ok)
        self.assertNotIn("deleteMany", repr(runner.call_args_list))
        self.assertNotIn("DEL", repr(runner.call_args_list))
