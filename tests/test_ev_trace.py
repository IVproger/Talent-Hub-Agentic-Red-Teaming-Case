import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from agentic_redteam.evidence.providers.trace import TraceProvider, LangfuseReader, OtelJsonReader


class TraceTests(unittest.TestCase):
    def config(self, backend="langfuse"):
        return {"backend": backend, "trace_id": "trace-1", "principal_from": {"kind": "argument", "name": "user"}}

    def test_backends_map_identical_tool_spans_and_exclude_preexisting_spans(self):
        old = {"id": "old", "name": "tool.read", "attributes": {"user": "1"}}
        new = {"id": "new", "name": "tool.read", "attributes": {"user": "2"}}
        results = []
        for backend in ("langfuse", "otel"):
            reader = Mock()
            reader.spans_for.side_effect = [[old], [old, new, {"name": "llm", "attributes": {}}]]
            provider = TraceProvider(self.config(backend), reader)
            results.append(provider.collect(provider.mark()))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(results[0]), 1)
        self.assertEqual(results[0][0].payload["tool"], "read")
        self.assertEqual(results[0][0].payload["principal"], "2")

    def test_reader_failure_propagates_and_none_binding_does_not_invent_principal(self):
        reader = Mock()
        reader.spans_for.side_effect = OSError("failed")
        with self.assertRaises(RuntimeError):
            TraceProvider(self.config(), reader).mark()
        reader.spans_for.side_effect = [[], [{"name": "tool.read", "attributes": {"user": "2"}}]]
        provider = TraceProvider({**self.config(), "principal_from": {"kind": "none"}}, reader)
        self.assertIsNone(provider.collect(provider.mark())[0].payload["principal"])

    def test_langfuse_v2_pagination_credentials_and_json_input(self):
        get = Mock(side_effect=[
            {"data": [{"id": "one", "traceId": "t", "name": "tool.read", "input": '{"user":"2"}'}], "meta": {"cursor": "next"}},
            {"data": [{"id": "two", "traceId": "t", "name": "tool.write", "input": {"user": "2"}}], "meta": {}},
        ])
        reader = LangfuseReader({"host": "http://langfuse", "public_key_env": "PUB", "secret_key_env": "SEC"},
                               get_json=get, environ={"PUB": "pub", "SEC": "private"})
        spans = reader.spans_for("t")
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0]["attributes"], {"user": "2"})
        url, headers = get.call_args.args
        self.assertEqual(urlsplit(url).path, "/api/public/v2/observations")
        self.assertEqual(parse_qs(urlsplit(url).query)["cursor"], ["next"])
        self.assertNotIn("private", url)
        self.assertTrue(headers["Authorization"].startswith("Basic "))

    def test_langfuse_rejects_incomplete_pagination(self):
        get = Mock(return_value={"data": [], "meta": {"cursor": "loop"}})
        reader = LangfuseReader({"host": "http://langfuse", "public_key_env": "PUB", "secret_key_env": "SEC"},
                               get_json=get, environ={"PUB": "p", "SEC": "s"})
        with self.assertRaises(RuntimeError):
            reader.spans_for("t")

    def test_otlp_jsonl_trace_filter_and_typed_attributes(self):
        trace_id = "1" * 32
        event = {"resourceSpans": [{"scopeSpans": [{"spans": [
            {"traceId": trace_id, "spanId": "a" * 16, "name": "tool.read", "attributes": [
                {"key": "user", "value": {"intValue": "2"}},
                {"key": "nested", "value": {"arrayValue": {"values": [{"boolValue": True}]}}}]},
            {"traceId": "2" * 32, "name": "tool.other", "attributes": []}]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spans.jsonl"
            path.write_text(json.dumps(event) + "\n")
            spans = OtelJsonReader({"path": str(path)}).spans_for(trace_id)
            self.assertEqual(len(spans), 1)
            self.assertEqual(spans[0]["attributes"], {"user": 2, "nested": [True]})
            path.write_text("truncated {")
            with self.assertRaises(RuntimeError):
                OtelJsonReader({"path": str(path)}).spans_for(trace_id)
