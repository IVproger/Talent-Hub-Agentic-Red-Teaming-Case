import unittest
import urllib.request

from agentic_redteam.evidence.base import EvidenceKind
from agentic_redteam.evidence.providers.http_canary import HttpCanaryProvider


class CanaryTests(unittest.TestCase):
    def test_real_callback_after_marker_and_close(self):
        provider = HttpCanaryProvider({"bind": "127.0.0.1:0"})
        self.addCleanup(provider.close)
        self.assertTrue(provider.calibrate().ok)
        with urllib.request.urlopen(provider.url_for("old"), timeout=2) as response:
            self.assertEqual(response.status, 204)
        marker = provider.mark()
        with urllib.request.urlopen(provider.url_for("T with + symbols"), timeout=2) as response:
            self.assertEqual(response.status, 204)
        observations = provider.collect(marker)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].kind, EvidenceKind.EXTERNAL_CALLBACK)
        self.assertEqual(observations[0].payload["token"], "T with + symbols")
        provider.close()
        self.assertFalse(provider.calibrate().ok)
        with self.assertRaises(RuntimeError):
            provider.collect(marker)

    def test_health_and_foreign_markers_are_not_callbacks(self):
        with HttpCanaryProvider({}) as first, HttpCanaryProvider({}) as second:
            marker = first.mark()
            with urllib.request.urlopen(first.bind_addr, timeout=2):
                pass
            self.assertEqual(first.collect(marker), [])
            with self.assertRaises(ValueError):
                first.collect(second.mark())

    def test_capacity_overflow_invalidates_evidence_instead_of_dropping_events(self):
        with HttpCanaryProvider({"max_events": 1}) as provider:
            marker = provider.mark()
            with urllib.request.urlopen(provider.url_for("first"), timeout=2):
                pass
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(provider.url_for("second"), timeout=2)
            caught.exception.close()
            with self.assertRaises(RuntimeError):
                provider.collect(marker)
