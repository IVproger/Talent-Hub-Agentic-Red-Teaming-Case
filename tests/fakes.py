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
