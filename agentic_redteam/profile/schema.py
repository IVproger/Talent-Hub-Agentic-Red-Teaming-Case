"""Target profile contracts and offline YAML validation.

Provider-specific configuration stays in mappings: loading a profile neither
imports a provider nor contacts the target or resolves environment secrets.
Frozen dataclasses prevent field reassignment; nested lists/maps remain ordinary
declarations, as required by the public contract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from ..errors import PipelineConfigurationError


_SEMVER = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", re.ASCII
)
_SCOPES = ("cross_user", "per_user", "session", "cross_session")


def _invalid(path: str, message: str) -> None:
    raise PipelineConfigurationError(f"Профиль: {path} — {message}.")


def _mapping(value: object, path: str) -> dict:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _invalid(path, "ожидается словарь со строковыми ключами")
    return value


def _list(value: object, path: str) -> list:
    if not isinstance(value, list):
        _invalid(path, "ожидается список")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(path, "ожидается непустая строка")
    return value


def _choice(value: object, choices: tuple, path: str) -> None:
    if value not in choices:
        _invalid(path, "допустимые значения: " + ", ".join(choices))


def _unique(values: list[str], path: str) -> None:
    if len(set(values)) != len(values):
        _invalid(path, "идентификаторы не должны повторяться")


@dataclass(frozen=True)
class ToolDecl:
    name: str
    args: list[str]
    sensitive: bool
    principal_from: dict


@dataclass(frozen=True)
class MemoryDecl:
    id: str
    scope: str | None
    scope_from: str | None
    read: dict
    record: dict


@dataclass(frozen=True)
class Boundary:
    id: str
    principal_attr: str
    principal_type: str
    claim: str


@dataclass(frozen=True)
class TargetProfile:
    name: str
    version: str
    adapter: str
    entrypoint: dict
    identities: dict
    isolation: list[Boundary]
    tools: list[ToolDecl]
    memory: list[MemoryDecl]
    modes: dict
    evidence: list[dict]
    attribution: str
    business: dict

    @classmethod
    def load(cls, path: str | Path) -> TargetProfile:
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            # Parser errors may contain YAML snippets with credentials.
            raise PipelineConfigurationError(
                "Не удалось прочитать YAML-профиль; проверьте файл и его синтаксис."
            ) from exc
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data):
        data = _mapping(data, "profile")
        surface = _mapping(data.get("surface", {}), "surface")
        tools = []
        for index, item in enumerate(_list(surface.get("tools", []), "surface.tools")):
            item = _mapping(item, f"surface.tools[{index}]")
            tools.append(ToolDecl(item.get("name"), item.get("args", []),
                                  item.get("sensitive", False),
                                  item.get("principal_from", {"kind": "none"})))
        memory = []
        for index, item in enumerate(_list(surface.get("memory", []), "surface.memory")):
            item = _mapping(item, f"surface.memory[{index}]")
            memory.append(MemoryDecl(item.get("id"), item.get("scope"),
                                     item.get("scope_from"), item.get("read", {}),
                                     item.get("record", {})))
        boundaries = []
        for index, item in enumerate(_list(data.get("isolation", []), "isolation")):
            item = _mapping(item, f"isolation[{index}]")
            principal = _mapping(item.get("principal", {}), f"isolation[{index}].principal")
            boundaries.append(Boundary(item.get("id"), principal.get("attribute"),
                                       principal.get("type", "string"), item.get("claim")))
        profile = cls(
            name=data.get("name"), version=data.get("version"), adapter=data.get("adapter"),
            entrypoint=data.get("entrypoint", {}), identities=data.get("identities", {}),
            isolation=boundaries, tools=tools, memory=memory, modes=data.get("modes", {}),
            evidence=data.get("evidence", []), attribution=data.get("attribution", "serialized"),
            business=data.get("business", {}),
        )
        profile.validate()
        return profile

    def validate(self) -> None:
        _text(self.name, "name")
        if not _SEMVER.fullmatch(_text(self.version, "version")):
            _invalid("version", "ожидается версия SemVer, например 1.0.0")
        _text(self.adapter, "adapter")
        entrypoint = _mapping(self.entrypoint, "entrypoint")
        base_url = _text(entrypoint.get("base_url"), "entrypoint.base_url")
        try:
            url = urlsplit(base_url)
            port = url.port
            valid_url = (url.scheme in ("http", "https") and url.hostname
                         and not url.username and not url.password
                         and not url.query and not url.fragment
                         and not any(char.isspace() for char in base_url)
                         and (port is None or port > 0))
        except ValueError:
            valid_url = False
        if not valid_url:
            _invalid("entrypoint.base_url", "ожидается HTTP(S) URL без учётных данных, query и fragment")
        for field in ("request", "response", "commit_memory"):
            if field in entrypoint:
                _mapping(entrypoint[field], f"entrypoint.{field}")
        _mapping(self.identities, "identities")
        for field in ("config", "principal", "credential", "roles"):
            if field in self.identities:
                _mapping(self.identities[field], f"identities.{field}")
        for index, boundary in enumerate(_list(self.isolation, "isolation")):
            path = f"isolation[{index}]"
            if not isinstance(boundary, Boundary):
                _invalid(path, "ожидается Boundary")
            for field in ("id", "principal_attr", "principal_type", "claim"):
                _text(getattr(boundary, field), f"{path}.{field}")
        _unique([item.id for item in self.isolation], "isolation")
        for index, tool in enumerate(_list(self.tools, "surface.tools")):
            path = f"surface.tools[{index}]"
            if not isinstance(tool, ToolDecl):
                _invalid(path, "ожидается ToolDecl")
            _text(tool.name, f"{path}.name")
            for arg in _list(tool.args, f"{path}.args"):
                _text(arg, f"{path}.args")
            _unique(tool.args, f"{path}.args")
            if not isinstance(tool.sensitive, bool):
                _invalid(f"{path}.sensitive", "ожидается boolean")
            source = _mapping(tool.principal_from, f"{path}.principal_from")
            _choice(source.get("kind"), ("argument", "call_context", "none"), f"{path}.principal_from.kind")
            if source["kind"] == "argument":
                _text(source.get("name"), f"{path}.principal_from.name")
        _unique([item.name for item in self.tools], "surface.tools")
        for index, store in enumerate(_list(self.memory, "surface.memory")):
            self._validate_memory(store, f"surface.memory[{index}]")
        _unique([item.id for item in self.memory], "surface.memory")
        for name, mode in _mapping(self.modes, "modes").items():
            _text(name, "modes")
            _mapping(mode, f"modes.{name}")
            _choice(mode.get("scope"), ("per_request", "per_deployment"), f"modes.{name}.scope")
            for field in ("body", "env"):
                if field in mode:
                    _mapping(mode[field], f"modes.{name}.{field}")
        for index, provider in enumerate(_list(self.evidence, "evidence")):
            path = f"evidence[{index}]"
            _mapping(provider, path)
            _text(provider.get("id"), f"{path}.id")
            _text(provider.get("provider"), f"{path}.provider")
            _mapping(provider.get("config", {}), f"{path}.config")
        _unique([item["id"] for item in self.evidence], "evidence")
        _choice(self.attribution, ("serialized", "correlation_id", "trace_context"), "attribution")
        _mapping(self.business, "business")
        for path, value in (("entrypoint", self.entrypoint), ("identities", self.identities),
                            ("modes", self.modes), ("evidence", self.evidence)):
            _validate_credentials(value, path)
        for store in self.memory:
            _validate_credentials(store.read, f"memory.{store.id}.read")

    @staticmethod
    def _validate_memory(store: MemoryDecl, path: str) -> None:
        if not isinstance(store, MemoryDecl):
            _invalid(path, "ожидается MemoryDecl")
        _text(store.id, f"{path}.id")
        if store.scope_from is None:
            _choice(store.scope, _SCOPES, f"{path}.scope")
        elif store.scope_from != "record" or store.scope is not None:
            _invalid(path, "нужен либо scope, либо scope_from: record")
        read = _mapping(store.read, f"{path}.read")
        _text(read.get("provider"), f"{path}.read.provider")
        _mapping(read.get("config", {}), f"{path}.read.config")
        record = _mapping(store.record, f"{path}.record")
        _text(record.get("content"), f"{path}.record.content")
        for field in ("key", "owner"):
            if record.get(field) is not None:
                _text(record[field], f"{path}.record.{field}")
        if store.scope_from == "record":
            scope = _mapping(record.get("scope"), f"{path}.record.scope")
            _text(scope.get("field"), f"{path}.record.scope.field")
            for value in _mapping(scope.get("map", {}), f"{path}.record.scope.map").values():
                _choice(value, _SCOPES, f"{path}.record.scope.map")


def _validate_credentials(value: object, path: str) -> None:
    """Catch explicit secret literals while retaining opaque provider configs.

    Secret material is acquired at runtime. Profiles may contain environment
    variable names (``*_env``) or credential templates such as ``Bearer {secret}``.
    This checks known credential fields, not arbitrary business/content strings.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _invalid(path, "ожидаются строковые ключи")
            if key.lower() in ("authorization", "proxy-authorization", "api_key", "api-key",
                               "x-api-key", "password", "secret", "token", "access_token",
                               "secret_key", "client_secret") and item:
                if not isinstance(item, str) or not re.fullmatch(
                    r"(?:Bearer |Basic )?\{[A-Za-z_][A-Za-z0-9_]*\}", item
                ):
                    _invalid(f"{path}.{key}", "секрет должен задаваться через *_env или шаблон credential")
            _validate_credentials(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_credentials(item, f"{path}[{index}]")
