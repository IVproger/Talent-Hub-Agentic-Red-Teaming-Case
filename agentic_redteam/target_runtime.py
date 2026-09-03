"""Read-only verification of the model used by the target stand.

The stand reads model settings when ``agent-api`` starts.  Its OpenAI-compatible
``model`` request field is not an execution override, so the red-team harness must
verify the live container instead of pretending to switch it per request.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable

from . import config
from .llm import LLMRoleConfig


class TargetConfigurationError(RuntimeError):
    """The live target is not using the selected model configuration."""


@dataclass(frozen=True)
class TargetModelState:
    base_url: str
    research_model: str
    summarization_model: str
    has_api_key: bool
    credential_valid: bool
    model_available: bool
    probe_error: str = ""


Runner = Callable[..., subprocess.CompletedProcess[str]]


class TargetRuntime:
    def __init__(self, compose_file: str | None = None, runner: Runner | None = None):
        self.compose_file = compose_file or config.COMPOSE_FILE
        self._runner = runner or subprocess.run

    def inspect(self) -> TargetModelState:
        script = """import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from app.config import get_settings

s = get_settings()
base = str(s.openai_base_url or '').rstrip('/')
key = str(s.openai_api_key or '')
headers = {'Accept': 'application/json', 'Authorization': f'Bearer {key}'}
credential_valid = True
model_available = False
probe_error = ''
try:
    if urlsplit(base).hostname in {'openrouter.ai', 'www.openrouter.ai'}:
        with urlopen(Request(base + '/key', headers=headers), timeout=3) as response:
            json.load(response)
    with urlopen(Request(base + '/models', headers=headers), timeout=3) as response:
        payload = json.load(response)
    models = payload.get('data', []) if isinstance(payload, dict) else []
    identifiers = {str(item.get('id')) for item in models if isinstance(item, dict)}
    wanted = str(s.research_model)
    if wanted.startswith('openai:'):
        wanted = wanted[len('openai:'):]
    model_available = wanted in identifiers
except Exception as exc:
    credential_valid = False
    probe_error = f'{exc.__class__.__name__}: provider readiness check failed'
print(json.dumps({
    'base_url': base,
    'research_model': s.research_model,
    'summarization_model': s.summarization_model,
    'has_api_key': bool(key),
    'credential_valid': credential_valid,
    'model_available': model_available,
    'probe_error': probe_error,
}))
"""
        try:
            result = self._runner(
                [
                    "docker", "compose", "-f", self.compose_file,
                    "exec", "-T", "agent-api", "python", "-c", script,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            data = json.loads(result.stdout.strip().splitlines()[-1])
            return TargetModelState(
                base_url=str(data.get("base_url", "")),
                research_model=str(data.get("research_model", "")),
                summarization_model=str(data.get("summarization_model", "")),
                has_api_key=bool(data.get("has_api_key", False)),
                credential_valid=bool(data.get("credential_valid", False)),
                model_available=bool(data.get("model_available", False)),
                probe_error=str(data.get("probe_error", "")),
            )
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            OSError,
            ValueError,
            IndexError,
        ) as exc:
            raise TargetConfigurationError(
                "Could not inspect target agent model. Start the stand and verify "
                f"the configured Compose file ({self.compose_file}) before running a scenario."
            ) from exc

    def assert_matches(self, selected: LLMRoleConfig) -> TargetModelState:
        if selected.normalized().temperature != 0:
            raise TargetConfigurationError(
                "The current target stand does not support a per-run temperature; use 0."
            )
        state = self.inspect()
        expected_url, expected_model = expected_target_settings(selected)
        actual_url = state.base_url.rstrip("/")
        model_mismatch = (
            state.research_model != expected_model
            or state.summarization_model != expected_model
        )
        missing_key = not state.has_api_key
        if (
            actual_url != expected_url.rstrip("/")
            or model_mismatch
            or missing_key
            or not state.credential_valid
            or not state.model_available
        ):
            raise TargetConfigurationError(
                "The target agent is not using the selected provider/model. "
                f"Expected OPENAI_BASE_URL={expected_url} and "
                f"RESEARCH_MODEL={expected_model}; live agent-api reports "
                f"OPENAI_BASE_URL={state.base_url or '<empty>'} and "
                f"RESEARCH_MODEL={state.research_model or '<empty>'}, "
                f"SUMMARIZATION_MODEL={state.summarization_model or '<empty>'}, and "
                f"API key configured={'yes' if state.has_api_key else 'no'}, "
                f"credential accepted={'yes' if state.credential_valid else 'no'}, and "
                f"model available={'yes' if state.model_available else 'no'}. Run "
                "`python -m agentic_redteam stand sync`, then repeat the check."
            )
        return state


def expected_target_settings(selected: LLMRoleConfig) -> tuple[str, str]:
    cfg = selected.normalized()
    if cfg.provider == "openrouter":
        base_url = cfg.base_url or "https://openrouter.ai/api/v1"
    else:
        # agent-api runs inside Docker; localhost would point back to the container.
        base_url = cfg.base_url or "http://host.docker.internal:11434/v1"
        if "localhost:11434" in base_url:
            base_url = base_url.replace("localhost:11434", "host.docker.internal:11434")
        if base_url.endswith("/api/chat"):
            base_url = base_url[: -len("/api/chat")] + "/v1"
        elif not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
    model = cfg.model if cfg.model.startswith("openai:") else f"openai:{cfg.model}"
    return base_url.rstrip("/"), model
