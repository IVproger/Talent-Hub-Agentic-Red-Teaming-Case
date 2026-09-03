"""HTTP client for the target agent-api (OpenAI-compatible + stand extras).

Handles the headless API-key path the stand's README only documents via browser
SSO: keys are minted directly through the stand's own modules inside the
agent-api container, bound to a chosen cus.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from typing import Any

from . import config

_MINT_SNIPPET = (
    "from app.memory.mongo import MongoMemoryStore\n"
    "from app.apikeys import generate_key\n"
    "raw, rec = generate_key({cus!r}, label={label!r})\n"
    "MongoMemoryStore().api_keys.create(rec)\n"
    "print(raw)\n"
)


def _compose(*args: str, compose_file: str | None = None) -> list[str]:
    return ["docker", "compose", "-f", compose_file or config.COMPOSE_FILE, *args]


def mint_key(
    cus: str,
    label: str = "redteam",
    compose_file: str | None = None,
) -> str:
    """Mint a long-term sk-genai key bound to `cus` (headless, no browser SSO)."""
    snippet = _MINT_SNIPPET.format(cus=cus, label=label)
    out = subprocess.run(
        _compose(
            "exec", "-T", "agent-api", "python", "-", compose_file=compose_file
        ),
        input=snippet,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    key = out.stdout.strip().splitlines()[-1]
    if not key.startswith("sk-genai-"):
        raise RuntimeError(f"unexpected key output: {out.stdout!r} / {out.stderr!r}")
    return key


class AgentApiClient:
    """One instance per (key, cus) — i.e. per identity."""

    def __init__(
        self,
        key: str,
        cus: str,
        base_url: str | None = None,
        timeout: int | None = None,
        telemetry: Any | None = None,
    ):
        self.key = key
        self.cus = cus
        self.base_url = (base_url or config.AGENT_API).rstrip("/")
        self.timeout = timeout or config.REQUEST_TIMEOUT
        self.telemetry = telemetry

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if self.telemetry is not None:
            headers.update(self.telemetry.propagation_headers())
        return headers

    def _post(self, content: str, session_id: str, auth_mode: str) -> dict:
        body = json.dumps({
            "messages": [{"role": "user", "content": content}],
            "auth_mode": auth_mode,
            "session_id": session_id,
        }).encode()
        observation = (
            self.telemetry.observation(
                "target.request",
                input={"session_id": session_id, "auth_mode": auth_mode},
                metadata={"method": "POST", "path": "/v1/chat/completions"},
            )
            if self.telemetry is not None
            else _noop_observation()
        )
        with observation as span:
            req = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=body,
                headers=self._headers(),
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.load(response)
            span.update(output={"status": "ok"})
            return payload

    def chat(self, content: str, session_id: str, auth_mode: str = "vulnerable") -> str:
        d = self._post(content, session_id, auth_mode)
        return d["choices"][0]["message"]["content"]

    def finalize(self, session_id: str) -> list[dict]:
        """Run the memory orchestrator; returns extracted facts (each with `scope`)."""
        observation = (
            self.telemetry.observation(
                "target.finalize",
                input={"session_id": session_id},
                metadata={"method": "POST", "path": "/v1/sessions/{session_id}/finalize"},
            )
            if self.telemetry is not None
            else _noop_observation()
        )
        with observation as span:
            req = urllib.request.Request(
                f"{self.base_url}/v1/sessions/{session_id}/finalize",
                data=b"",
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                d = json.load(response)
            span.update(output={"facts": len(d.get("facts") or [])})
        return d.get("facts") or []


class _NoopSpan:
    def update(self, **_values) -> None:
        return None


class _NoopContext:
    def __enter__(self):
        return _NoopSpan()

    def __exit__(self, *_args):
        return False


def _noop_observation() -> _NoopContext:
    return _NoopContext()
