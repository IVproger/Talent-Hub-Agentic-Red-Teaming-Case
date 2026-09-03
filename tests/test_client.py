from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from agentic_redteam.client import AgentApiClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(
            {"choices": [{"message": {"content": "ok"}}]}
        ).encode("utf-8")


class FakeTelemetry:
    @contextmanager
    def observation(self, *_args, **_kwargs):
        yield type("Span", (), {"update": lambda self, **_values: None})()

    def propagation_headers(self):
        return {
            "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
            "tracestate": "vendor=value",
        }


class AgentApiClientTests(unittest.TestCase):
    def test_custom_target_endpoint_is_used(self):
        client = AgentApiClient(
            "sk-genai-test", "1001", "http://target.test:9999/", timeout=17
        )
        with patch("urllib.request.urlopen", return_value=FakeResponse()) as opened:
            self.assertEqual(client.chat("hello", "session"), "ok")
        request = opened.call_args.args[0]
        self.assertEqual(
            request.full_url, "http://target.test:9999/v1/chat/completions"
        )
        self.assertEqual(opened.call_args.kwargs["timeout"], 17)

    def test_w3c_trace_context_is_forwarded_without_custom_headers(self):
        client = AgentApiClient(
            "sk-genai-test",
            "1001",
            "http://target.test:9999",
            telemetry=FakeTelemetry(),
        )
        with patch("urllib.request.urlopen", return_value=FakeResponse()) as opened:
            client.chat("hello", "session")
        request = opened.call_args.args[0]
        self.assertEqual(
            request.get_header("Traceparent"),
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        )
        self.assertEqual(request.get_header("Tracestate"), "vendor=value")
        self.assertIsNone(request.get_header("X-Langfuse-Trace-Id"))


if __name__ == "__main__":
    unittest.main()
