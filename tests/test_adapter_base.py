from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from agentic_redteam.adapters.base import (
    AdapterFeature, Principal, TargetAdapter, TargetSession, TargetUnavailable,
    UnsupportedFeature,
)
from agentic_redteam.doctor import CheckResult


class _ScriptedSession:
    """Local contract fixture; shared tests/fakes.py belongs to task 0.0."""

    def __init__(self, principal, session_id, features, script):
        self.principal = principal
        self.session_id = session_id
        self.features = features
        self.script = iter(script)

    def send(self, message: str) -> str:
        response = next(self.script)
        if isinstance(response, Exception):
            raise response
        return response

    def commit_memory(self) -> list[dict]:
        if AdapterFeature.MEMORY_COMMIT not in self.features:
            raise UnsupportedFeature("Цель не поддерживает commit_memory.")
        return [{"content": "saved"}]


class _ScriptedAdapter:
    def __init__(self, features, script):
        self.features = frozenset(features)
        self.script = script
        self.closed = False

    def preflight(self) -> list[CheckResult]:
        return [CheckResult("target", True, "Цель доступна.")]

    def open_session(self, role: str, session_id: str, mode: str) -> TargetSession:
        return _ScriptedSession(Principal("agent_id", role), session_id,
                                self.features, self.script)

    def close(self) -> None:
        self.closed = True


class AdapterContractTests(unittest.TestCase):
    def test_structural_adapter_opens_session_with_identity_and_script(self):
        adapter = _ScriptedAdapter({AdapterFeature.SESSIONS}, ["first", "second"])
        self.assertIsInstance(adapter, TargetAdapter)
        session = adapter.open_session("attacker", "session-a", "vulnerable")
        self.assertIsInstance(session, TargetSession)
        self.assertEqual(session.principal, Principal("agent_id", "attacker"))
        self.assertEqual(session.session_id, "session-a")
        self.assertEqual(session.send("hello"), "first")
        self.assertEqual(session.send("again"), "second")
        self.assertTrue(adapter.preflight()[0].ok)
        adapter.close()
        self.assertTrue(adapter.closed)

    def test_optional_memory_commit_requires_feature(self):
        for features, supported in ((set(), False), ({AdapterFeature.MEMORY_COMMIT}, True)):
            with self.subTest(supported=supported):
                session = _ScriptedAdapter(features, []).open_session("a", "s", "default")
                if supported:
                    self.assertEqual(session.commit_memory(), [{"content": "saved"}])
                else:
                    with self.assertRaises(UnsupportedFeature):
                        session.commit_memory()

    def test_transport_failure_remains_distinct_from_unsupported_feature(self):
        session = _ScriptedAdapter(set(), [TargetUnavailable("Таймаут цели.")]).open_session(
            "a", "s", "default"
        )
        with self.assertRaises(TargetUnavailable):
            session.send("hello")
        self.assertTrue(issubclass(TargetUnavailable, RuntimeError))
        self.assertTrue(issubclass(UnsupportedFeature, RuntimeError))
        self.assertFalse(issubclass(TargetUnavailable, UnsupportedFeature))

    def test_principal_is_frozen_and_preserves_decimal_string(self):
        principal = Principal("user_id", "0012")
        self.assertEqual(principal.value, "0012")
        with self.assertRaises(FrozenInstanceError):
            principal.value = "12"

    def test_feature_values_are_stable_strings(self):
        self.assertEqual({item.value for item in AdapterFeature}, {
            "sessions", "memory_commit", "mode_per_request", "mode_per_deployment",
        })
        self.assertEqual(str(AdapterFeature.SESSIONS), "sessions")

    def test_incomplete_objects_do_not_implement_protocols(self):
        self.assertNotIsInstance(object(), TargetAdapter)
        self.assertNotIsInstance(object(), TargetSession)


if __name__ == "__main__":
    unittest.main()
