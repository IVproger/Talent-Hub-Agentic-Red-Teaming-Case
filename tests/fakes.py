"""Shared test fakes.

`FakeAdapter` and `FakeEvidenceProvider` are added alongside their protocols
(Tasks 2.1 / 3.1); here we ship the dependency-free `FakeLLM` and `FakeRunner`.
"""
from __future__ import annotations

import subprocess
from typing import Any


class FakeLLM:
    """Deterministic LLM: returns scripted completions in order."""

    def __init__(self, outputs: list[str]):
        self._outputs = list(outputs)
        self._index = 0

    def complete(self, prompt: str) -> str:
        output = self._outputs[self._index]
        self._index += 1
        return output


class FakeRunner:
    """Stands in for `subprocess.run`: returns scripted stdout in order."""

    def __init__(self, outputs: list[str]):
        self._outputs = list(outputs)
        self._index = 0

    def __call__(self, args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess:
        stdout = self._outputs[self._index]
        self._index += 1
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


class FakeSession:
    """Satisfies TargetSession. Scripted responses; commit_memory gated by features."""

    def __init__(self, principal, session_id, responses, features):
        self.principal = principal
        self.session_id = session_id
        self._responses = list(responses)
        self._index = 0
        self._features = features

    def send(self, message: str) -> str:
        r = self._responses[self._index]
        self._index += 1
        if isinstance(r, Exception):
            raise r
        return r

    def commit_memory(self) -> list[dict]:
        from agentic_redteam.adapters.base import AdapterFeature, UnsupportedFeature
        if AdapterFeature.MEMORY_COMMIT not in self._features:
            raise UnsupportedFeature("target has no memory commit")
        return []


class FakeAdapter:
    """Satisfies TargetAdapter. `roles`: role->principal value; `responses`: per send."""

    def __init__(self, roles, responses, features=frozenset()):
        self.features = features
        self._roles = roles
        self._responses = responses

    def preflight(self):
        return []

    def open_session(self, role: str, session_id: str, mode: str):
        from agentic_redteam.adapters.base import Principal
        return FakeSession(Principal("cus", self._roles[role]), session_id, self._responses, self.features)

    def close(self):
        pass


class FakeEvidenceSource:
    """Runner-facing evidence seam: mark() + collect_facts()->Facts + reset().

    The real EvidenceBundle (Task 3.6, oushtt) implements this interface.
    """

    def __init__(self, facts_sequence):
        self._facts = list(facts_sequence)
        self._collected = 0
        self._marks = 0
        self.resets = 0

    def mark(self):
        from agentic_redteam.evidence.base import Marker
        self._marks += 1
        return Marker(token=str(self._marks))

    def collect_facts(self, since):
        facts = self._facts[self._collected]
        self._collected += 1
        return facts

    def reset(self):
        self.resets += 1


class FakeTelemetry:
    """Records observation names; optionally raises to prove fail-open."""

    def __init__(self, raises=False):
        self.raises = raises
        self.names: list[str] = []

    def observation(self, name, **_kw):
        if self.raises:
            raise RuntimeError("telemetry down")
        self.names.append(name)
        from contextlib import nullcontext
        return nullcontext()


class FakeEvidenceProvider:
    """Raw provider contract; independent of the runner-facing evidence source."""

    def __init__(self, kind, observations=(), calibration=None):
        from agentic_redteam.evidence.base import CalibrationResult
        self.kind = kind
        self.observations = list(observations)
        self.calibration = calibration if calibration is not None else CalibrationResult(True)
        self._marks = 0

    def calibrate(self):
        return self.calibration

    def mark(self):
        from agentic_redteam.evidence.base import Marker
        self._marks += 1
        return Marker(str(self._marks))

    def collect(self, since):
        return list(self.observations)
