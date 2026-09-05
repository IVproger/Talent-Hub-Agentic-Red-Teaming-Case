"""Crash-tolerant, per-run file storage for security scenario executions."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from ..redaction import redact_data, redact_secrets


class StorageError(RuntimeError):
    pass


class RunStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def create(self, run_id: str) -> Path:
        _validate_run_id(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        run_dir = (self.root / run_id).resolve()
        if run_dir.parent != self.root:
            raise StorageError("Run id would escape the configured output directory.")
        try:
            run_dir.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise StorageError(f"Run directory already exists: {run_dir}") from exc
        return run_dir

    def write_json(self, run_dir: Path, name: str, value: Any) -> Path:
        return self.write_text(
            run_dir,
            name,
            json.dumps(redact_data(_jsonable(value)), ensure_ascii=False, indent=2) + "\n",
        )

    def write_jsonl(self, run_dir: Path, name: str, rows: list[Any]) -> Path:
        text = "".join(
            json.dumps(redact_data(_jsonable(row)), ensure_ascii=False) + "\n" for row in rows
        )
        return self.write_text(run_dir, name, text)

    def write_text(self, run_dir: Path, name: str, text: str) -> Path:
        target = _safe_child(run_dir, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return target

    def list_runs(self) -> list[dict]:
        if not self.root.exists():
            return []
        rows: list[dict] = []
        for run_dir in sorted(
            (item for item in self.root.iterdir() if item.is_dir()), reverse=True
        ):
            status_path = run_dir / "status.json"
            try:
                data = json.loads(status_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("run_id"), str)
                    or not isinstance(data.get("status"), str)
                    or data["run_id"] != run_dir.name
                    or data["status"]
                    not in {"pending", "running", "completed", "failed", "interrupted"}
                ):
                    raise ValueError("status.json has inconsistent run metadata")
                data["run_dir"] = str(run_dir)
                rows.append(data)
            except (OSError, ValueError):
                rows.append(
                    {
                        "run_id": run_dir.name,
                        "status": "invalid",
                        "message": "Run metadata is missing or invalid.",
                        "run_dir": str(run_dir),
                    }
                )
        return rows

    def load_json(self, run_dir: str | Path, name: str) -> Any:
        return json.loads(_safe_child(Path(run_dir).resolve(), name).read_text(encoding="utf-8"))

    def write_campaign(self, run_dir: Path, campaign: Any) -> Path:
        return self.write_json(run_dir, "campaign.json", campaign)

    def append_transcript(self, run_dir: str | Path, entry: Any) -> Path:
        target = _safe_child(Path(run_dir).resolve(), "transcript.jsonl")
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(redact_data(_jsonable(entry)), ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return target


def _safe_child(parent: Path, name: str) -> Path:
    if Path(name).name != name:
        raise StorageError(f"Artifact name must be a file name, got: {name}")
    target = (parent / name).resolve()
    if target.parent != parent.resolve():
        raise StorageError("Artifact path would escape the run directory.")
    return target


def _validate_run_id(run_id: str) -> None:
    if not run_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in run_id):
        raise StorageError("Run id may contain only letters, numbers, '-' and '_'.")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
