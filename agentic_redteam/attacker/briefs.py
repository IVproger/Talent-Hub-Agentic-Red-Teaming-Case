"""AttackBrief: зафиксированное задание автономному атакующему агенту.

Brief — единица атаки нового цикла. Он генерируется из профиля цели и
описаний стандартов, валидируется (схема YAML + ссылки на сущности профиля)
и фиксируется до кампании: повторные запуски и сравнение режимов используют
один и тот же набор brief с неизменными критериями успеха.

Схема — ровно пять полей из задачи; неизвестные поля отклоняются, чтобы
judge никогда не получил скрытых инструкций в лишних полях.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..errors import PipelineConfigurationError
from ..profile.schema import TargetProfile
from .standards import validate_refs

BRIEF_FIELDS = ("id", "standard_refs", "objective", "success_criteria", "guidance")
_ID_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
_TOOL_MENTION = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _invalid(message: str) -> None:
    raise PipelineConfigurationError(f"AttackBrief: {message}.")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} — ожидается непустая строка")
    return value


@dataclass(frozen=True)
class AttackBrief:
    id: str
    standard_refs: list[str]
    objective: str
    success_criteria: str
    guidance: str

    @classmethod
    def from_mapping(cls, data: object) -> "AttackBrief":
        if not isinstance(data, dict):
            _invalid("ожидается YAML-отображение (mapping)")
        unknown = sorted(set(data) - set(BRIEF_FIELDS))
        missing = [name for name in BRIEF_FIELDS if name not in data]
        if missing:
            _invalid("не хватает полей: " + ", ".join(missing))
        if unknown:
            _invalid("неизвестные поля: " + ", ".join(unknown))
        refs = data["standard_refs"]
        if not isinstance(refs, list) or not refs or not all(
            isinstance(ref, str) for ref in refs
        ):
            _invalid("standard_refs — ожидается непустой список строк")
        brief = cls(
            id=_text(data["id"], "id"),
            standard_refs=list(refs),
            objective=_text(data["objective"], "objective"),
            success_criteria=_text(data["success_criteria"], "success_criteria"),
            guidance=_text(data["guidance"], "guidance"),
        )
        brief.validate()
        return brief

    @classmethod
    def load(cls, path: str | Path) -> "AttackBrief":
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            _invalid(f"не удалось прочитать YAML: {path} ({exc})")
        return cls.from_mapping(data)

    def validate(self) -> None:
        if not _ID_SLUG.fullmatch(self.id):
            _invalid(f"id '{self.id}' — ожидается slug из строчных букв, цифр и '-'")
        try:
            validate_refs(self.standard_refs)
        except ValueError as exc:
            _invalid(str(exc))

    def to_mapping(self) -> dict:
        return {
            "id": self.id,
            "standard_refs": list(self.standard_refs),
            "objective": self.objective,
            "success_criteria": self.success_criteria,
            "guidance": self.guidance,
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(self.to_mapping(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return target

    def validate_against_profile(self, profile: TargetProfile) -> None:
        """Проверить ссылки на сущности профиля.

        Строго проверяются значения принципалов (``attr=value`` по атрибутам
        границ изоляции). Эвристические упоминания ``name(...)`` в свободном
        тексте не доказывают вызов инструмента; см. profile_warnings().
        """
        text = "\n".join((self.objective, self.success_criteria, self.guidance))
        known_principals = _known_principals(profile)
        for boundary in profile.isolation:
            pattern = re.compile(
                rf"\b{re.escape(boundary.principal_attr)}="
                r"([A-Za-z0-9_.:-]*[A-Za-z0-9_:-])"
            )
            for match in pattern.finditer(text):
                if match.group(1) not in known_principals:
                    _invalid(
                        f"'{match.group(0)}' ссылается на принципала, которого нет "
                        f"в ролях профиля (известны: {', '.join(sorted(known_principals))})"
                    )
    def profile_warnings(self, profile: TargetProfile) -> list[str]:
        """Advisory only: prose notation is not an executable tool call."""
        text = "\n".join((self.objective, self.success_criteria, self.guidance))
        known = {tool.name for tool in profile.tools}
        known.update(profile.identities.get("roles", {}))
        known.update(store.id for store in profile.memory)
        warnings = []
        for match in _TOOL_MENTION.finditer(text):
            if match.group(1) not in known:
                warnings.append(
                    f"Упоминание '{match.group(1)}(...)' не соответствует инструменту, "
                    "роли или хранилищу профиля; проверьте смысл вручную."
                )
                known.add(match.group(1))
        return warnings


def _known_principals(profile: TargetProfile) -> set[str]:
    attributes = {boundary.principal_attr for boundary in profile.isolation}
    values: set[str] = set()
    roles = profile.identities.get("roles", {})
    if isinstance(roles, dict):
        for role in roles.values():
            if not isinstance(role, dict):
                continue
            for key, value in role.items():
                if key in attributes and value is not None:
                    values.add(str(value))
    return values


def save_briefs(directory: str | Path, briefs: list[AttackBrief]) -> list[Path]:
    """Зафиксировать набор brief: один YAML-файл на brief.

    Фиксация одношаговая: существующие файлы не перезаписываются, чтобы
    зафиксированный набор не мог незаметно измениться между кампаниями.
    """
    briefs = list(briefs)
    if not briefs:
        _invalid("пустой набор brief не фиксируется")
    root = Path(directory)
    if root.exists():
        if not root.is_dir():
            _invalid(f"путь для brief не является каталогом: {root}")
        if any(root.iterdir()):
            _invalid(f"каталог brief должен быть пустым: {root}")
    seen: set[str] = set()
    targets: list[tuple[AttackBrief, Path]] = []
    # Сначала проверяем весь набор, и только потом пишем файлы:
    # ошибка в позднем brief не оставит частично сохранённый набор.
    for brief in briefs:
        if not isinstance(brief, AttackBrief):
            _invalid("набор содержит не AttackBrief")
        brief.validate()
        if brief.id in seen:
            _invalid(f"дублирующийся id '{brief.id}'")
        seen.add(brief.id)
        targets.append((brief, root / f"{brief.id}.yaml"))
    return [brief.save(target) for brief, target in targets]


def load_briefs(source: str | Path) -> list[AttackBrief]:
    """Load one brief YAML file or every brief YAML in a directory."""
    root = Path(source)
    if root.is_file():
        if root.suffix.lower() not in {".yaml", ".yml"}:
            _invalid(f"файл brief должен иметь расширение .yaml или .yml: {root}")
        return [AttackBrief.load(root)]
    if not root.is_dir():
        _invalid(f"файл или каталог brief не найден: {root}")
    briefs: list[AttackBrief] = []
    seen: set[str] = set()
    paths = sorted(
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    )
    for path in paths:
        brief = AttackBrief.load(path)
        if brief.id in seen:
            _invalid(f"дублирующийся id '{brief.id}'")
        seen.add(brief.id)
        briefs.append(brief)
    if not briefs:
        _invalid(f"в каталоге нет ни одного brief YAML: {root}")
    return briefs
