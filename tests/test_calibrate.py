import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from agentic_redteam.adapters.base import AdapterFeature, Principal
from agentic_redteam.doctor import CheckResult
from agentic_redteam.evidence.base import CalibrationResult, EvidenceKind
from agentic_redteam.evidence.calibrate import check, verify
from agentic_redteam.normalize.facts import Facts, ObservedMemoryWrite, Persistence


class CalibrationTests(unittest.TestCase):
    def test_check_is_read_only_and_reports_each_provider(self):
        source = Mock(kind=EvidenceKind.TOOL_CALLS)
        source.calibrate.return_value = CalibrationResult(True, "matched")
        memory = Mock(kind=EvidenceKind.MEMORY_SNAPSHOT)
        memory.calibrate.return_value = CalibrationResult(False, "empty")
        bundle = SimpleNamespace(providers={"calls": source, "memory": memory})
        adapter = Mock()
        adapter.preflight.return_value = [CheckResult("target", True, "ready")]
        results = check(bundle, adapter)
        self.assertEqual([result.name for result in results], ["target", "calls", "memory"])
        self.assertFalse(results[-1].blocking)
        adapter.open_session.assert_not_called()
        source.mark.assert_not_called()
        source.collect.assert_not_called()

    def probe(self, scope, visible_to_reader=True, writer_visible=True):
        state = {}
        writer = Mock(principal=Principal("user", "1"), session_id="writer")
        writer.send.side_effect = lambda message: state.update(marker=re.search(r"MOROK_VERIFY_[a-f0-9]+", message)[0])
        reader = Mock(principal=Principal("user", "2"), session_id="reader")
        reader.send.return_value = "I can see the marker"  # never used as evidence
        adapter = Mock(features=frozenset({AdapterFeature.MEMORY_COMMIT}))
        adapter.open_session.side_effect = [writer, reader]
        source = Mock(kind=EvidenceKind.MEMORY_SNAPSHOT)
        source.config = {"store_id": "s", "record": {"content": "text"}, "scope": scope,
                         "visibility": {"module": "target", "factory": "Store", "method": "read"}}
        source.read_visible.side_effect = lambda principal, session_id: (
            [{"text": state["marker"]}] if (writer_visible if principal.value == "1" else visible_to_reader) else [])
        bundle = Mock(profile=SimpleNamespace(entrypoint={}, modes={"default": {}}), providers={"memory:s": source})
        bundle.capabilities.return_value = {"memory_snapshot", "session_reset"}
        bundle.snapshot_memory.side_effect = lambda: Facts(memory_writes=[ObservedMemoryWrite(
            "s", scope, "key", state["marker"], "1", Persistence.CONFIRMED, {})])
        return bundle, adapter

    def test_verify_uses_target_memory_views_and_cleans_up(self):
        bundle, adapter = self.probe("cross_user", True)
        self.assertTrue(verify(bundle, adapter)[0].ok)
        self.assertEqual(bundle.reset.call_count, 2)

    def test_visibility_mismatch_fails_despite_positive_model_response(self):
        bundle, adapter = self.probe("cross_user", False)
        self.assertFalse(verify(bundle, adapter)[0].ok)
        self.assertEqual(bundle.reset.call_count, 2)

    def test_per_user_isolation_requires_writer_positive_control(self):
        bundle, adapter = self.probe("per_user", False)
        self.assertTrue(verify(bundle, adapter)[0].ok)
        bundle, adapter = self.probe("per_user", False, writer_visible=False)
        self.assertFalse(verify(bundle, adapter)[0].ok)

    def test_missing_reset_or_visibility_prevents_target_mutation(self):
        bundle, adapter = self.probe("cross_user")
        bundle.capabilities.return_value = {"memory_snapshot"}
        self.assertFalse(verify(bundle, adapter)[0].ok)
        adapter.open_session.assert_not_called()
        bundle.reset.assert_not_called()

    def test_read_failure_still_resets_and_cannot_pass(self):
        bundle, adapter = self.probe("cross_user")
        bundle.providers["memory:s"].read_visible.side_effect = RuntimeError("failed")
        self.assertFalse(verify(bundle, adapter)[0].ok)
        self.assertEqual(bundle.reset.call_count, 2)
