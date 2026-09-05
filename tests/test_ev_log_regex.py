import json
import tempfile
import unittest
from pathlib import Path

from agentic_redteam.evidence.providers.log_regex import LogRegexProvider
from tests.fakes import FakeRunner


class LogRegexTests(unittest.TestCase):
    def config(self):
        return {"source": {"kind": "docker-log", "compose_file": "compose.yml", "service": "api"},
                "pattern": r'"GET /clients/(\d+)', "captures": ["principal"],
                "tool": "read_client", "args": {"user": "{principal}"},
                "calibration": {"expected_principal": "1001"}}

    def test_only_lines_after_marker_become_observations(self):
        before = 'old "GET /clients/1001\n'
        after = before + 'new "GET /clients/1002\n'
        source = LogRegexProvider(self.config(), FakeRunner([before, after]))
        observation = source.collect(source.mark())[0]
        self.assertEqual(observation.payload["principal"], "1002")
        self.assertEqual(observation.payload["args"], {"user": "1002"})
        self.assertEqual(observation.payload["tool"], "read_client")
        self.assertEqual(observation.raw, 'new "GET /clients/1002')

    def test_file_source_and_rotation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calls.log"
            path.write_text('first "GET /clients/1001\n')
            source = LogRegexProvider({**self.config(), "source": {"kind": "file", "path": str(path)}})
            marker = source.mark()
            path.write_text('rotated "GET /clients/1002\n')
            with self.assertRaises(RuntimeError):
                source.collect(marker)

    def test_cli_json_selects_messages(self):
        config = {**self.config(), "source": {"kind": "cli-json", "command": ["logs", "--json"], "select": "events"}}
        source = LogRegexProvider(config, FakeRunner(["{\"events\": []}", json.dumps({"events": [{"message": '"GET /clients/1002'}]})]))
        self.assertEqual(source.collect(source.mark())[0].payload["principal"], "1002")

    def test_calibration_needs_matching_known_principal(self):
        for line, ok in (('"GET /clients/1001', True), ('"GET /clients/1002', False), ("", False)):
            with self.subTest(line=line):
                self.assertEqual(LogRegexProvider(self.config(), FakeRunner([line])).calibrate().ok, ok)

    def test_missing_sources_do_not_look_like_empty_logs(self):
        source = LogRegexProvider({**self.config(), "source": {"kind": "file", "path": "/missing-morok-log"}})
        with self.assertRaises(RuntimeError):
            source.mark()
