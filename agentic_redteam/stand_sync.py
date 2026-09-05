"""Synchronize the target stand model settings from the canonical target YAML."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

import yaml

from .errors import PipelineConfigurationError
from .stand_bootstrap import target_model_from_config
from .target_runtime import TargetRuntime, expected_target_settings


MANAGED_KEYS = ("OPENAI_BASE_URL", "RESEARCH_MODEL", "SUMMARIZATION_MODEL")
_ASSIGNMENT = re.compile(
    r"^(?P<prefix>\s*(?:export\s+)?)"
    r"(?P<key>OPENAI_BASE_URL|RESEARCH_MODEL|SUMMARIZATION_MODEL)"
    r"(?P<separator>\s*=\s*)(?P<value>.*?)(?P<newline>\r?\n)?$"
)
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9._:/+-]+$")


class StandSyncError(RuntimeError):
    """The target configuration could not be synchronized safely."""


@dataclass(frozen=True)
class StandSyncChange:
    key: str
    old: str | None
    new: str


@dataclass(frozen=True)
class StandSyncResult:
    changed: bool
    dry_run: bool
    env_file: str
    compose_file: str
    changes: tuple[StandSyncChange, ...]
    recreated: bool = False
    verified: bool = False

    def to_dict(self) -> dict:
        value = asdict(self)
        value["changes"] = [asdict(item) for item in self.changes]
        return value


Runner = Callable[..., subprocess.CompletedProcess[str]]


def sync_stand(
    target_config: str | Path,
    *,
    dry_run: bool = False,
    runner: Runner | None = None,
    target_runtime: TargetRuntime | None = None,
) -> StandSyncResult:
    """Apply the bootstrap profile model to the stand's three env settings."""
    config_path = Path(target_config).expanduser().resolve()
    raw = _load_yaml(config_path)
    target = raw.get("target")
    if not isinstance(target, Mapping):
        raise StandSyncError("target configuration must contain a target mapping.")
    compose_value = target.get("compose_file")
    if not isinstance(compose_value, str) or not compose_value.strip():
        raise StandSyncError("target.compose_file must be a non-empty path.")
    compose_file = Path(compose_value).expanduser()
    if not compose_file.is_absolute():
        candidates = [parent / compose_file for parent in config_path.parents]
        compose_file = next(
            (candidate for candidate in candidates if candidate.is_file()),
            candidates[0],
        )
    compose_file = compose_file.resolve()
    if not compose_file.is_file():
        raise StandSyncError(f"Compose file does not exist: {compose_file}")

    try:
        selected = target_model_from_config(raw, config_path, require_profile=True)
        selected.validate(require_credentials=False)
        base_url, model = expected_target_settings(selected)
    except (OSError, PipelineConfigurationError, ValueError) as exc:
        raise StandSyncError(f"Invalid profile target model configuration: {exc}") from exc
    expected = {
        "OPENAI_BASE_URL": base_url,
        "RESEARCH_MODEL": model,
        "SUMMARIZATION_MODEL": model,
    }
    for key, value in expected.items():
        if not _SAFE_VALUE.fullmatch(value) or "\n" in value or "\r" in value:
            raise StandSyncError(f"Unsafe value for managed setting {key}.")

    env_file = compose_file.parent / ".env"
    if not env_file.is_file():
        raise StandSyncError(
            f"Stand env file does not exist: {env_file}. Copy .env.example first."
        )
    with env_file.open("r", encoding="utf-8", newline="") as handle:
        original = handle.read()
    updated, changes = _render_updated_env(original, expected)
    changed = bool(changes)
    base_result = StandSyncResult(
        changed=changed,
        dry_run=dry_run,
        env_file=str(env_file),
        compose_file=str(compose_file),
        changes=tuple(changes),
    )
    if dry_run or not changed:
        if not dry_run:
            runtime = target_runtime or TargetRuntime(str(compose_file), runner=runner)
            runtime.assert_matches(selected)
            return StandSyncResult(**{**asdict(base_result), "changes": tuple(changes), "verified": True})
        return base_result

    _atomic_write(env_file, updated)
    command_runner = runner or subprocess.run
    try:
        command_runner(
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "up",
                "-d",
                "--no-deps",
                "--force-recreate",
                "agent-api",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=180,
        )
        runtime = target_runtime or TargetRuntime(str(compose_file), runner=runner)
        runtime.assert_matches(selected)
    except Exception as exc:
        raise StandSyncError(
            "stand/.env was updated, but agent-api recreation or verification failed: "
            f"{exc}"
        ) from exc
    return StandSyncResult(
        changed=True,
        dry_run=False,
        env_file=str(env_file),
        compose_file=str(compose_file),
        changes=tuple(changes),
        recreated=True,
        verified=True,
    )


def _load_yaml(path: Path) -> Mapping:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise StandSyncError(f"Could not read target configuration: {path}") from exc
    if not isinstance(raw, Mapping):
        raise StandSyncError("Target configuration must be a YAML mapping.")
    return raw


def _render_updated_env(
    original: str, expected: Mapping[str, str]
) -> tuple[str, list[StandSyncChange]]:
    lines = original.splitlines(keepends=True)
    locations: dict[str, int] = {}
    current: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        key = match.group("key")
        if key in locations:
            raise StandSyncError(f"Managed setting {key} is defined more than once.")
        locations[key] = index
        current[key] = match.group("value")

    changes: list[StandSyncChange] = []
    newline = "\r\n" if "\r\n" in original else "\n"
    had_final_newline = original.endswith(("\n", "\r"))
    for key in MANAGED_KEYS:
        value = expected[key]
        old = current.get(key)
        if old == value:
            continue
        changes.append(StandSyncChange(key=key, old=old, new=value))
        if key in locations:
            index = locations[key]
            match = _ASSIGNMENT.match(lines[index])
            assert match is not None
            ending = match.group("newline") or ""
            lines[index] = (
                f"{match.group('prefix')}{key}{match.group('separator')}{value}{ending}"
            )
        else:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            lines.append(f"{key}={value}{newline}")

    rendered = "".join(lines)
    if not had_final_newline and original and rendered.endswith(("\n", "\r")):
        rendered = rendered.rstrip("\r\n")
    return rendered, changes


def _atomic_write(path: Path, text: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
