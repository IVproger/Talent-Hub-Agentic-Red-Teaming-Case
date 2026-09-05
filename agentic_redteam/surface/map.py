"""Declared target structure plus source-specific calibration results."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..generation.composer import Unsupported, compose
from ..generation.coverage import coverage
from ..generation.template import load_templates

PROVIDER_KINDS = {
    "db-query": "memory_snapshot",
    "json-file": "memory_snapshot",
    "log-regex": "tool_calls",
    "trace": "tool_calls",
    "http-canary": "external_callback",
    "state-reset": "session_reset",
}


def declared_capabilities(profile):
    declared = {
        PROVIDER_KINDS[item["provider"]]
        for item in profile.evidence
        if item.get("provider") in PROVIDER_KINDS
    }
    if profile.memory:
        declared.add("memory_snapshot")
    return declared


def build_surface(profile, check_results=()):
    def value(result, key, default=None):
        return result.get(key, default) if isinstance(result, dict) else getattr(result, key, default)

    checks = {value(result, "name"): result for result in check_results}

    def state(key):
        result = checks.get(key)
        if result is None:
            return {
                "status": "заявлен, но не подтверждён",
                "reason": "Калибровка не выполнялась для этого компонента.",
            }
        return {
            "status": "подключён" if value(result, "ok") else "недоступен",
            "reason": value(result, "message", ""),
        }

    evidence = [
        {
            "id": item["id"],
            "kind": PROVIDER_KINDS.get(item["provider"], "unknown"),
            "provider": item["provider"],
            **state(item["id"]),
        }
        for item in profile.evidence
    ]
    entrypoint = {
        "id": "entrypoint:chat",
        "path": profile.entrypoint.get("chat_path", "/v1/chat/completions"),
        **state("target"),
    }
    tools = [
        {
            "id": "tool:" + tool.name,
            "name": tool.name,
            "args": tool.args,
            "sensitive": tool.sensitive,
            "priority": "проверка доступа" if tool.sensitive else "обычный",
            "principal_from": tool.principal_from,
            # An aggregate audit probe does not prove that each tool works.
            **state("tool:" + tool.name),
        }
        for tool in profile.tools
    ]
    memory = [
        {
            "id": item.id,
            "node_id": "memory:" + item.id,
            "scope": item.scope or item.scope_from,
            **state("memory:" + item.id),
        }
        for item in profile.memory
    ]
    templates = load_templates(Path(__file__).resolve().parents[2] / "templates")
    channels = _input_channels(profile, templates, state)
    integrations = _integrations(profile, state)
    relationships = [
        {
            "from": channel["id"],
            "to": entrypoint["id"],
            "kind": "delivers_to",
        }
        for channel in channels
    ]
    relationships += [
        {"from": entrypoint["id"], "to": tool["id"], "kind": "may_call"}
        for tool in tools
    ]
    relationships += [
        {
            "from": entrypoint["id"],
            "to": item["node_id"],
            "kind": "reads_or_writes",
        }
        for item in memory
    ]
    relationships += [
        {
            "from": "evidence:" + item["id"],
            "to": "target",
            "kind": "observes",
        }
        for item in evidence
    ]
    relationships += [
        {"from": item["id"], "to": component, "kind": "supports"}
        for item in integrations
        for component in item["components"]
    ]
    return {
        "profile": f"{profile.name}@{profile.version}",
        "adapter": profile.adapter,
        "base_url": profile.entrypoint.get("base_url"),
        "tools": tools,
        "memory": memory,
        "roles": list(profile.identities.get("roles", {})),
        "entrypoints": [entrypoint],
        "input_channels": channels,
        "integrations": integrations,
        "relationships": relationships,
        "isolation": [
            {
                "id": boundary.id,
                "claim": boundary.claim,
                "principal": boundary.principal_attr,
            }
            for boundary in profile.isolation
        ],
        "evidence": evidence,
        "modes": {
            name: declaration.get("scope")
            for name, declaration in profile.modes.items()
        },
        "attribution": profile.attribution,
        "review_required": profile.entrypoint.get("review_required", []),
        "coverage": _standard_coverage(profile, templates),
    }


def _input_channels(profile, templates, state) -> list[dict]:
    """Return declared and applicable template delivery channels."""
    aliases = {
        "user_message": "chat",
        "tool_result": "tool-result",
        "file": "document",
    }
    names = set(profile.entrypoint.get("input_channels", []))
    for template in templates:
        if not isinstance(compose(template, profile), Unsupported):
            names.update(aliases.get(item, item.replace("_", "-"))
                         for item in template.delivery)
    if not names:
        names.add("chat")
    return [
        {
            "id": "channel:" + name,
            "name": name,
            **state("target" if name == "chat" else "channel:" + name),
        }
        for name in sorted(names)
    ]


def _integrations(profile, state) -> list[dict]:
    """Extract external systems from memory and evidence declarations."""
    integrations: dict[str, dict] = {}

    def add(name: str, kind: str, check_id: str, component: str) -> None:
        key = f"integration:{name}"
        item = integrations.setdefault(key, {
            "id": key,
            "name": name,
            "kind": kind,
            "components": [],
            **state(check_id),
        })
        if component not in item["components"]:
            item["components"].append(component)

    target_model = profile.entrypoint.get("target_model", {})
    if isinstance(target_model, dict) and target_model.get("provider"):
        add(str(target_model["provider"]), "model-provider", "target_model", "target")

    for memory in profile.memory:
        config = memory.read.get("config", {})
        driver = config.get("driver")
        service = config.get("service")
        if driver or service:
            add(str(service or driver), str(driver or "memory-store"),
                "memory:" + memory.id, "memory:" + memory.id)
    for evidence in profile.evidence:
        config = evidence.get("config", {})
        source = config.get("source", {})
        if isinstance(source, dict) and source.get("service"):
            add(str(source["service"]), str(source.get("kind", "external-service")),
                evidence["id"], "evidence:" + evidence["id"])
        for kind in ("mongo", "redis"):
            nested = config.get(kind, {})
            if isinstance(nested, dict) and nested.get("service"):
                add(str(nested["service"]), kind, evidence["id"],
                    "evidence:" + evidence["id"])
    return sorted(integrations.values(), key=lambda item: item["id"])


def _standard_coverage(profile, templates) -> dict:
    """Summarise the existing composer gate without claiming full coverage."""
    report = coverage(templates, profile)
    rows = [asdict(row) for row in report.rows]
    provable = {
        row.standard
        for row in report.rows
        if row.status == "composed"
        and row.ceiling == "proven"
        and row.standard.startswith("ASI")
    }
    return {
        "standard": "owasp-agentic-2026",
        "provable": len(provable),
        "total": 10,
        "items": rows,
        "note": "Наличие шаблона не означает полное покрытие пункта стандарта.",
    }
