"""Headless stand key minting, ported from client.py without legacy imports."""
from __future__ import annotations

import copy
import subprocess

from ...errors import PipelineConfigurationError
from .base import Credential
from .static import principal_for, render_credential


_MINT_SNIPPET = (
    "from app.memory.mongo import MongoMemoryStore\n"
    "from app.apikeys import generate_key\n"
    "raw, rec = generate_key({principal!r}, label={label!r})\n"
    "MongoMemoryStore().api_keys.create(rec)\n"
    "print(raw)\n"
)


class DockerExecMintProvider:
    def __init__(self, config: dict, runner=subprocess.run):
        self.config = copy.deepcopy(config)
        self.runner = runner
        self.command_config = self.config.get("config", {})
        for field in ("compose_file", "service"):
            if not isinstance(self.command_config.get(field), str) or not self.command_config[field]:
                raise PipelineConfigurationError(f"docker-exec-mint требует config.{field}.")

    def acquire(self, role: str) -> Credential:
        principal = principal_for(self.config, role)
        snippet = _MINT_SNIPPET.format(principal=principal.value, label=f"redteam-{role}")
        command = ["docker", "compose", "-f", self.command_config["compose_file"],
                   "exec", "-T", self.command_config["service"], "python", "-"]
        try:
            output = self.runner(command, input=snippet, capture_output=True,
                                 text=True, check=True, timeout=30)
            lines = output.stdout.strip().splitlines()
            key = lines[-1] if lines else ""
            if output.returncode or not key.startswith("sk-genai-") or len(key) <= len("sk-genai-"):
                raise ValueError
        except (OSError, subprocess.SubprocessError, ValueError):
            raise RuntimeError("Не удалось выпустить корректный ключ цели через docker-exec-mint.") from None
        credential = render_credential(self.config, role, principal, key)
        if not credential.headers:
            return Credential(principal, {"Authorization": f"Bearer {key}"}, credential.body_fields)
        return credential

    def release(self, credential: Credential) -> None:
        """Minted long-lived keys follow the stand's existing key lifecycle."""
