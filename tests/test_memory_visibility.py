import json
import unittest
from unittest.mock import Mock

from agentic_redteam.adapters.base import Principal
from agentic_redteam.evidence.providers.visibility import read_target_view
from tests.fakes import FakeRunner


class MemoryVisibilityTests(unittest.TestCase):
    def config(self):
        return {"visibility": {"compose_file": "compose.yml", "service": "api", "module": "target.memory",
                               "factory": "Store", "member": "semantic", "method": "list_for_user",
                               "arguments": ["{principal}"]}}

    def test_reads_target_method_with_principal_as_data(self):
        runner = Mock(wraps=FakeRunner(['[{"text":"marker"}]\n']))
        result = read_target_view(self.config(), Principal("user", "2'quoted"), "session", runner)
        self.assertEqual(result, [{"text": "marker"}])
        self.assertEqual(json.loads(runner.call_args.kwargs["input"])["arguments"], ["2'quoted"])
        self.assertNotIn("2'quoted", repr(runner.call_args.args))

    def test_malformed_target_view_is_not_invisibility(self):
        with self.assertRaises(RuntimeError):
            read_target_view(self.config(), Principal("user", "2"), "s", FakeRunner(["broken"]))
