import copy
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

from agentic_redteam.adapters.base import AdapterFeature, TargetUnavailable, UnsupportedFeature
from agentic_redteam.adapters.http_chat import HttpChatAdapter
from agentic_redteam.adapters.identities.base import Credential
from agentic_redteam.adapters.base import Principal
from agentic_redteam.profile.schema import TargetProfile


class HttpChatTests(unittest.TestCase):
    def setUp(self):
        self.profile = TargetProfile.load(Path(__file__).with_name("data") / "profile_stand.yaml")
        self.identities = Mock()
        self.identities.acquire.return_value = Credential(Principal("user", "1"), {"Authorization": "Bearer private-key"}, {"from": "actor"})
        self.transport = Mock(return_value={"choices": [{"message": {"content": "hello"}}]})

    def test_request_templates_mode_override_and_response_array_path(self):
        original = copy.deepcopy(self.profile)
        adapter = HttpChatAdapter(self.profile, self.identities, self.transport)
        session = adapter.open_session("attacker", "session-1", "protected")
        self.assertEqual(session.send("literal {braces}"), "hello")
        url, body, headers = self.transport.call_args.args
        self.assertEqual(url, "http://localhost:8600/v1/chat/completions")
        self.assertEqual(body, {"messages": [{"role": "user", "content": "literal {braces}"}],
                                "session_id": "session-1", "auth_mode": "protected", "from": "actor"})
        self.assertEqual(headers["Authorization"], "Bearer private-key")
        self.assertEqual(self.profile, original)
        self.assertIn(AdapterFeature.MEMORY_COMMIT, adapter.features)
        adapter.open_session("attacker", "session-2", "protected")
        self.identities.acquire.assert_called_once_with("attacker")
        adapter.close()
        self.identities.release.assert_called_once()
        with self.assertRaises(TargetUnavailable):
            session.send("after close")

    def test_commit_memory_and_unsupported_feature(self):
        self.transport.return_value = {"facts": [{"content": "persisted"}]}
        session = HttpChatAdapter(self.profile, self.identities, self.transport).open_session("attacker", "a/b", "protected")
        self.assertEqual(session.commit_memory(), [{"content": "persisted"}])
        self.assertIn("a%2Fb/finalize", self.transport.call_args.args[0])
        entrypoint = {k: v for k, v in self.profile.entrypoint.items() if k != "commit_memory"}
        session = HttpChatAdapter(replace(self.profile, entrypoint=entrypoint), self.identities, self.transport).open_session("attacker", "s", "protected")
        with self.assertRaises(UnsupportedFeature):
            session.commit_memory()

    def test_transport_and_invalid_responses_are_target_errors_without_secret_details(self):
        for failure in (URLError("private-key"), TimeoutError("private-key")):
            self.transport.side_effect = failure
            session = HttpChatAdapter(self.profile, self.identities, self.transport).open_session("attacker", "s", "protected")
            with self.assertRaises(TargetUnavailable) as caught:
                session.send("hi")
            self.assertNotIn("private-key", str(caught.exception))
        self.transport.side_effect = None
        for result in ({"choices": []}, {"choices": [{"message": {"content": 4}}]}):
            self.transport.return_value = result
            with self.assertRaises(TargetUnavailable):
                session.send("hi")

    def test_deployment_modes_require_explicit_controller(self):
        profile = replace(self.profile, modes={"protected": {"scope": "per_deployment", "env": {"ENFORCE": "on"}}})
        with self.assertRaises(UnsupportedFeature):
            HttpChatAdapter(profile, self.identities, self.transport).open_session("attacker", "s", "protected")
        switcher = Mock()
        adapter = HttpChatAdapter(profile, self.identities, self.transport, mode_switcher=switcher)
        adapter.open_session("attacker", "s", "protected")
        adapter.open_session("attacker", "t", "protected")
        switcher.assert_called_once_with("protected", profile.modes["protected"])

    def test_preflight_is_get_and_never_mints_credentials(self):
        profile = replace(self.profile, entrypoint={**self.profile.entrypoint, "preflight": {"path": "/healthz"}})
        result = HttpChatAdapter(profile, self.identities, self.transport).preflight()
        self.assertTrue(result[0].ok)
        self.assertEqual(self.transport.call_args.kwargs["method"], "GET")
        self.identities.acquire.assert_not_called()

    def test_active_trace_context_is_propagated_to_the_target(self):
        telemetry = Mock()
        telemetry.propagation_headers.return_value = {
            "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
        }
        session = HttpChatAdapter(
            self.profile, self.identities, self.transport, telemetry=telemetry
        ).open_session("attacker", "s", "vulnerable")
        session.send("hi")
        headers = self.transport.call_args.args[2]
        self.assertEqual(headers["traceparent"], telemetry.propagation_headers.return_value["traceparent"])

    def test_broken_trace_propagation_is_fail_open(self):
        telemetry = Mock()
        telemetry.propagation_headers.side_effect = RuntimeError("collector down")
        session = HttpChatAdapter(
            self.profile, self.identities, self.transport, telemetry=telemetry
        ).open_session("attacker", "s", "vulnerable")
        self.assertEqual(session.send("hi"), "hello")
