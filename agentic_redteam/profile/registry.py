"""Versioned profile files; published versions cannot be overwritten."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path

import yaml

from ..errors import PipelineConfigurationError
from .schema import TargetProfile, _SEMVER


def to_mapping(profile: TargetProfile) -> dict:
    """Restore the YAML representation (which differs from dataclass nesting)."""
    data = asdict(profile)
    data["surface"] = {"tools": data.pop("tools"), "memory": data.pop("memory")}
    data["isolation"] = [
        {"id": b.id, "principal": {"attribute": b.principal_attr, "type": b.principal_type},
         "claim": b.claim} for b in profile.isolation
    ]
    return data


class ProfileRegistry:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def _path(self, name: str, version: str) -> Path:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise PipelineConfigurationError("Недопустимое имя профиля.")
        if not isinstance(version, str) or not _SEMVER.fullmatch(version):
            raise PipelineConfigurationError("Версия профиля должна соответствовать SemVer.")
        path = self.root / name / f"{version}.yaml"
        if path.parent.is_symlink() or path.is_symlink() or path.resolve().parent.parent != self.root:
            raise PipelineConfigurationError("Путь профиля выходит за пределы реестра или является ссылкой.")
        return path

    def list(self) -> list[tuple[str, str]]:
        if not self.root.exists():
            return []
        result = []
        for path in sorted(self.root.glob("*/*.yaml")):
            self.load(path.parent.name, path.stem)
            result.append((path.parent.name, path.stem))
        return result

    def load(self, name: str, version: str) -> TargetProfile:
        profile = TargetProfile.load(self._path(name, version))
        if (profile.name, profile.version) != (name, version):
            raise PipelineConfigurationError("Имя или версия внутри профиля не совпадает с адресом в реестре.")
        return profile

    def save(self, profile: TargetProfile) -> Path:
        profile.validate()
        path = self._path(profile.name, profile.version)
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".profile-", delete=False) as output:
                temporary = Path(output.name)
                yaml.safe_dump(to_mapping(profile), output, allow_unicode=True, sort_keys=False)
                output.flush()
                os.fsync(output.fileno())
            # Atomic publication without replacing an existing version.
            os.link(temporary, path)
        except OSError as exc:
            raise PipelineConfigurationError(
                "Не удалось сохранить профиль: проверьте доступ и отсутствие этой версии в реестре."
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path
