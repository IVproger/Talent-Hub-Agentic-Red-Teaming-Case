"""HTTP client for the target agent-api (OpenAI-compatible + stand extras).

Handles the headless API-key path the stand's README only documents via browser
SSO: keys are minted directly through the stand's own modules inside the
agent-api container, bound to a chosen cus.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request

from . import config

_MINT_SNIPPET = (
    "from app.memory.mongo import MongoMemoryStore\n"
    "from app.apikeys import generate_key\n"
    "raw, rec = generate_key({cus!r}, label={label!r})\n"
    "MongoMemoryStore().api_keys.create(rec)\n"
    "print(raw)\n"
)


def _compose(*args: str) -> list[str]:
    return ["docker", "compose", "-f", config.COMPOSE_FILE, *args]


def mint_key(cus: str, label: str = "redteam") -> str:
    """Mint a long-term sk-genai key bound to `cus` (headless, no browser SSO)."""
    snippet = _MINT_SNIPPET.format(cus=cus, label=label)
    out = subprocess.run(
        _compose("exec", "-T", "agent-api", "python", "-"),
        input=snippet, capture_output=True, text=True, check=True,
    )
    key = out.stdout.strip().splitlines()[-1]
    if not key.startswith("sk-genai-"):
        raise RuntimeError(f"unexpected key output: {out.stdout!r} / {out.stderr!r}")
    return key


class AgentApiClient:
    """One instance per (key, cus) — i.e. per identity."""

    def __init__(self, key: str, cus: str):
        self.key = key
        self.cus = cus

    def _post(self, content: str, session_id: str, auth_mode: str) -> dict:
        body = json.dumps({
            "messages": [{"role": "user", "content": content}],
            "auth_mode": auth_mode,
            "session_id": session_id,
        }).encode()
        req = urllib.request.Request(
            f"{config.AGENT_API}/v1/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT) as r:
            return json.load(r)

    def chat(self, content: str, session_id: str, auth_mode: str = "vulnerable") -> str:
        d = self._post(content, session_id, auth_mode)
        return d["choices"][0]["message"]["content"]

    def finalize(self, session_id: str) -> list[dict]:
        """Run the memory orchestrator; returns extracted facts (each with `scope`)."""
        req = urllib.request.Request(
            f"{config.AGENT_API}/v1/sessions/{session_id}/finalize", data=b"",
            headers={"Authorization": f"Bearer {self.key}"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT) as r:
            d = json.load(r)
        return d.get("facts") or []
