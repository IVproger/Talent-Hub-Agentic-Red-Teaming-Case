"""Declared target structure plus source-specific calibration results."""

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
    return {
        "profile": f"{profile.name}@{profile.version}",
        "adapter": profile.adapter,
        "base_url": profile.entrypoint.get("base_url"),
        "tools": [
            {
                "name": tool.name,
                "args": tool.args,
                "sensitive": tool.sensitive,
                "principal_from": tool.principal_from,
                # An aggregate audit probe does not prove that each tool works.
                **state("tool:" + tool.name),
            }
            for tool in profile.tools
        ],
        "memory": [
            {
                "id": memory.id,
                "scope": memory.scope or memory.scope_from,
                **state("memory:" + memory.id),
            }
            for memory in profile.memory
        ],
        "roles": list(profile.identities.get("roles", {})),
        "entrypoints": [
            {
                "path": profile.entrypoint.get("chat_path", "/v1/chat/completions"),
                **state("target"),
            }
        ],
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
    }
