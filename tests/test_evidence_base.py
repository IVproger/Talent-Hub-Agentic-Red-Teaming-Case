from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, asdict

from agentic_redteam.evidence.base import (
    CalibrationResult, EvidenceKind, EvidenceProvider, Marker, Observation,
)


class _ScriptedEvidenceProvider:
    """Local fixture, independent of task 0.0's shared FakeEvidenceProvider."""

    def __init__(self, kind, observations, calibration=None):
        self.kind = kind
        self.observations = observations
        self.calibration = calibration if calibration is not None else CalibrationResult(True)
        self.collected_since = None

    def calibrate(self) -> CalibrationResult:
        return self.calibration

    def mark(self) -> Marker:
        return Marker("offset-42")

    def collect(self, since: Marker) -> list[Observation]:
        self.collected_since = since
        return list(self.observations)


class EvidenceContractTests(unittest.TestCase):
    def test_structural_provider_supports_mark_collect_and_calibration(self):
        observation = Observation(EvidenceKind.TOOL_CALLS, {"principal": "1002"}, "raw event")
        provider = _ScriptedEvidenceProvider(EvidenceKind.TOOL_CALLS, [observation])
        self.assertIsInstance(provider, EvidenceProvider)
        marker = provider.mark()
        self.assertIsInstance(marker, Marker)
        self.assertEqual(provider.collect(marker), [observation])
        self.assertEqual(provider.collected_since, marker)
        self.assertTrue(provider.calibrate().ok)

    def test_failed_calibration_retains_explanation(self):
        result = CalibrationResult(False, "Поле principal не обнаружено.")
        provider = _ScriptedEvidenceProvider(EvidenceKind.TOOL_CALLS, [], result)
        self.assertFalse(provider.calibrate().ok)
        self.assertEqual(provider.calibrate().message, "Поле principal не обнаружено.")

    def test_observation_preserves_payload_and_raw_source_for_normalization(self):
        payload = {"documents": [{"_id": "1", "content": "fact", "scope": "global"}]}
        raw = '{"documents":[{"_id":"1","content":"fact","scope":"global"}]}'
        observation = Observation(EvidenceKind.MEMORY_SNAPSHOT, payload, raw)
        self.assertEqual(observation.payload, payload)
        self.assertEqual(observation.raw, raw)
        restored = json.loads(json.dumps(asdict(observation)))
        self.assertEqual(restored["kind"], "memory_snapshot")
        self.assertEqual(restored["payload"], payload)

    def test_contract_dataclasses_are_frozen(self):
        for obj, attr, value in (
            (Marker("cursor"), "token", "changed"),
            (Observation(EvidenceKind.AUDIT_LOG, {}, "raw"), "raw", "changed"),
            (CalibrationResult(True), "ok", False),
        ):
            with self.subTest(type=type(obj).__name__), self.assertRaises(FrozenInstanceError):
                setattr(obj, attr, value)

    def test_evidence_kind_values_cover_exactly_the_frozen_contract(self):
        self.assertEqual({item.value for item in EvidenceKind}, {
            "memory_snapshot", "tool_calls", "external_callback", "audit_log", "session_reset",
        })
        self.assertEqual(str(EvidenceKind.TOOL_CALLS), "tool_calls")

    def test_object_without_provider_methods_does_not_implement_protocol(self):
        self.assertNotIsInstance(object(), EvidenceProvider)


if __name__ == "__main__":
    unittest.main()
