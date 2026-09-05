import json
import subprocess
import unittest
from unittest.mock import Mock

from agentic_redteam.evidence.base import EvidenceKind
from agentic_redteam.evidence.providers.db_query import DbQueryProvider
from tests.fakes import FakeRunner


class DbQueryTests(unittest.TestCase):
    def setUp(self):
        self.config = {"driver": "mongo", "db": "memory", "collection": "facts", "store_id": "s",
                       "compose_file": "stand/compose.yml", "service": "mongo",
                       "record": {"key": "_id", "content": "text"}, "scope": "cross_user"}

    def test_collect_retains_raw_documents_and_uses_declared_database(self):
        raw = json.dumps({"facts": [{"_id": "1", "text": "fact"}]})
        runner = Mock(wraps=FakeRunner([raw]))
        provider = DbQueryProvider(self.config, runner)
        result = provider.collect(provider.mark())[0]
        self.assertEqual(result.kind, EvidenceKind.MEMORY_SNAPSHOT)
        self.assertEqual(result.payload["documents"], [{"_id": "1", "text": "fact"}])
        self.assertEqual(result.raw, raw)
        self.assertIn("getCollection(\"facts\")", runner.call_args.kwargs["input"])
        self.assertNotIn("delete", runner.call_args.kwargs["input"])

    def test_calibration_checks_actual_content_not_just_connectivity(self):
        for documents, ok in (([{"_id": "1", "text": "fact"}], True),
                               ([{"_id": "1", "other": "fact"}], False),
                               ([{"_id": "1", "text": None}], False), ([], False)):
            with self.subTest(documents=documents):
                provider = DbQueryProvider(self.config, FakeRunner([json.dumps(documents)]))
                self.assertEqual(provider.calibrate().ok, ok)

    def test_failed_or_malformed_queries_are_not_empty_successes(self):
        for runner in (FakeRunner(["broken"]), Mock(side_effect=subprocess.TimeoutExpired("db", 1))):
            provider = DbQueryProvider(self.config, runner)
            with self.assertRaises(RuntimeError):
                provider.collect(provider.mark())

    def test_uri_secret_is_in_environment_not_process_arguments(self):
        runner = Mock(wraps=FakeRunner(["[]"]))
        config = {**self.config, "uri_env": "TARGET_DB"}
        provider = DbQueryProvider(config, runner, environ={"TARGET_DB": "mongodb://user:private@host/db"})
        provider.collect(provider.mark())
        self.assertNotIn("private", repr(runner.call_args.args))
        self.assertEqual(runner.call_args.kwargs["env"]["MOROK_MONGO_URI"], "mongodb://user:private@host/db")

    def test_unsupported_driver_fails_explicitly(self):
        with self.assertRaises(NotImplementedError):
            DbQueryProvider({**self.config, "driver": "postgres"})
