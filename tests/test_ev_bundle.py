import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from agentic_redteam.adapters.base import UnsupportedFeature
from agentic_redteam.evidence.base import EvidenceKind, Observation
from agentic_redteam.evidence.bundle import EvidenceBundle
from agentic_redteam.evidence.providers.json_file import JsonFileProvider
from agentic_redteam.profile.schema import TargetProfile
from tests.fakes import FakeEvidenceProvider


def snapshot(documents):
    return Observation(EvidenceKind.MEMORY_SNAPSHOT, {"store_id": "store", "documents": documents,
        "record": {"key": "id", "content": "text"}, "scope": "cross_user"}, "raw")


class BundleTests(unittest.TestCase):
    def test_capability_gate_and_runner_seam(self):
        source = FakeEvidenceProvider(EvidenceKind.TOOL_CALLS, [Observation(EvidenceKind.TOOL_CALLS,
            {"tool": "read", "principal": "2", "args": {"user": 2}}, "line")])
        bundle = EvidenceBundle({"calls": source})
        self.assertEqual(bundle.capabilities(), {"tool_calls"})
        self.assertEqual(bundle.supports([{"type": "memory_write"}]), (False, ["нет memory_snapshot"]))
        self.assertTrue(bundle.supports([{"type": "tool_principal_mismatch"}])[0])
        facts = bundle.collect_facts(bundle.mark())
        self.assertEqual(facts.tool_calls[0].principal, "2")
        self.assertEqual(facts.tool_calls[0].args, {"user": "2"})
        with self.assertRaises(UnsupportedFeature):
            bundle.reset()

    def test_memory_is_diffed_per_store_including_changes_to_existing_key(self):
        source = FakeEvidenceProvider(EvidenceKind.MEMORY_SNAPSHOT)
        source.collect = Mock(side_effect=[
            [snapshot([{"id": "1", "text": "old"}, {"id": "2", "text": "unchanged"}])],
            [snapshot([{"id": "1", "text": "poison"}, {"id": "2", "text": "unchanged"}, {"id": "3", "text": "new"}])],
        ])
        bundle = EvidenceBundle([source])
        facts = bundle.collect_all(bundle.mark_all())
        self.assertEqual({item.content for item in facts.memory_writes}, {"poison", "new"})
        self.assertEqual({item.store_id for item in facts.memory_writes}, {"store"})
        self.assertFalse(bundle.supports([{"type": "memory_write"}])[0])

    def test_callbacks_are_normalized_and_markers_are_single_use(self):
        source = FakeEvidenceProvider(EvidenceKind.EXTERNAL_CALLBACK, [Observation(EvidenceKind.EXTERNAL_CALLBACK,
            {"token": "T", "source": "host"}, "callback")])
        bundle = EvidenceBundle([source])
        marker = bundle.mark()
        self.assertEqual(bundle.collect_facts(marker).callbacks[0].token, "T")
        with self.assertRaises(ValueError):
            bundle.collect_facts(marker)

    def test_provider_failure_never_becomes_partial_success(self):
        source = FakeEvidenceProvider(EvidenceKind.TOOL_CALLS)
        source.collect = Mock(side_effect=RuntimeError("unavailable"))
        bundle = EvidenceBundle([source])
        with self.assertRaises(RuntimeError):
            bundle.collect_facts(bundle.mark())

    def test_profile_principal_binding_controls_normalization(self):
        profile = TargetProfile.load(Path(__file__).with_name("data") / "profile_stand.yaml")
        source = FakeEvidenceProvider(EvidenceKind.TOOL_CALLS, [Observation(EvidenceKind.TOOL_CALLS,
            {"tool": "get_portfolio", "principal": "wrong", "args": {"cus": "1002"}}, "raw")])
        bundle = EvidenceBundle([source], profile=profile)
        self.assertEqual(bundle.collect_facts(bundle.mark()).tool_calls[0].principal, "1002")

    def test_factory_builds_bootstrap_without_target_io(self):
        profile = TargetProfile.load(Path(__file__).resolve().parents[1] / "profiles/genai-invest-stand/1.0.0.yaml")
        runner = Mock(side_effect=AssertionError("constructor must not execute target commands"))
        with EvidenceBundle.from_profile(profile, runner=runner) as bundle:
            self.assertEqual(bundle.capabilities(), {"memory_snapshot", "tool_calls", "session_reset"})
            runner.assert_not_called()

    def test_unknown_goal_is_not_silently_supported(self):
        self.assertFalse(EvidenceBundle([]).supports([{"type": "typo"}])[0])

    def test_json_file_snapshot_preserves_cross_session_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text('{"memories": []}')
            source = JsonFileProvider({"path": str(path), "select": "memories[]", "store_id": "file",
                                       "record": {"key": "id", "content": "text"}, "scope": "cross_session"})
            bundle = EvidenceBundle([source])
            marker = bundle.mark()
            path.write_text('{"memories": [{"id": "1", "text": "fact"}]}')
            fact = bundle.collect_facts(marker).memory_writes[0]
            self.assertEqual((fact.store_id, fact.scope, fact.content), ("file", "cross_session", "fact"))
