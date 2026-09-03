from __future__ import annotations

import importlib.util
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "stand" / "app" / "observability.py"
)
SPEC = importlib.util.spec_from_file_location("stand_observability_test", MODULE_PATH)
stand_observability = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(stand_observability)


class FakeObservation:
    def update(self, **_values):
        return None


class FakeClient:
    def __init__(self):
        self.started = []

    @contextmanager
    def start_as_current_observation(self, **values):
        self.started.append(values)
        yield FakeObservation()


class StandObservabilityTests(unittest.TestCase):
    def test_regular_traffic_does_not_create_a_trace(self):
        client = FakeClient()
        with patch.object(stand_observability, "_client", return_value=client):
            with stand_observability.request_observation(
                {}, "stand.chat", user_id="1001", session_id="session"
            ):
                pass
        self.assertEqual(client.started, [])

    def test_w3c_parent_context_enables_target_observations(self):
        client = FakeClient()
        headers = {
            "traceparent": (
                "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
            )
        }
        with patch.object(stand_observability, "_client", return_value=client):
            with stand_observability.request_observation(
                headers,
                "stand.chat",
                user_id="1001",
                session_id="session",
                input={"Authorization": "Bearer secret"},
            ):
                with stand_observability.observation("stand.react.loop"):
                    pass
        self.assertEqual(
            [item["name"] for item in client.started],
            ["stand.chat", "stand.react.loop"],
        )
        self.assertEqual(client.started[0]["input"]["Authorization"], "[redacted]")
        self.assertEqual(client.started[0]["metadata"]["agent_role"], "target")
        self.assertEqual(client.started[1]["metadata"]["agent_role"], "target")


if __name__ == "__main__":
    unittest.main()
