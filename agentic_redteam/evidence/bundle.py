"""Provider composition, capability gating, and raw-observation normalization."""
from __future__ import annotations

import copy
import json
import subprocess
from uuid import uuid4

from ..adapters.base import UnsupportedFeature
from ..assertions.registry import REQUIRED, required_kinds
from ..errors import PipelineConfigurationError
from ..normalize.facts import Facts, ObservedCallback, ObservedToolCall
from ..normalize.memdiff import diff as memory_diff
from ..normalize.projection import dotted, principal_of, project_memory
from .base import EvidenceKind, Marker, Observation


class EvidenceBundle:
    def __init__(self, providers, profile=None):
        self.providers = dict(providers) if isinstance(providers, dict) else {
            f"{provider.kind}:{index}": provider for index, provider in enumerate(providers)}
        self.profile = profile
        self._tools = {tool.name: tool for tool in profile.tools} if profile else {}
        self._memory = {store.id: store for store in profile.memory} if profile else {}
        self._windows = {}
        self._closed = False
        self.last_observations = {}

    @classmethod
    def from_profile(cls, profile, *, runner=subprocess.run, readers=None, provider_factories=None):
        from .providers.db_query import DbQueryProvider
        from .providers.http_canary import HttpCanaryProvider
        from .providers.json_file import JsonFileProvider
        from .providers.log_regex import LogRegexProvider
        from .providers.state_reset import StateResetProvider
        from .providers.trace import TraceProvider

        profile.validate()
        factories = {
            "db_query": lambda config: DbQueryProvider(config, runner),
            "log_regex": lambda config: LogRegexProvider(config, runner),
            "http_canary": HttpCanaryProvider,
            "json_file": JsonFileProvider,
            "state_reset": lambda config: StateResetProvider(config, runner),
            "trace": TraceProvider,
            "langfuse": lambda config: TraceProvider({**config, "backend": "langfuse"}),
            "otel_trace": lambda config: TraceProvider({**config, "backend": "otel"}),
        }
        factories.update(provider_factories or {})
        declarations = copy.deepcopy(profile.evidence)
        for store in profile.memory:
            declarations.append({"id": f"memory:{store.id}", "provider": store.read["provider"],
                "config": {**store.read.get("config", {}), "store_id": store.id,
                           "record": store.record, "scope": store.scope}})
        providers = {}
        try:
            for declaration in declarations:
                name = declaration["id"]
                kind = declaration["provider"].replace("-", "_")
                if name in providers or kind not in factories:
                    raise PipelineConfigurationError("Дублированный id или неподдерживаемый evidence-провайдер.")
                config = copy.deepcopy(declaration.get("config", {}))
                if readers and name in readers and kind in ("trace", "langfuse", "otel_trace"):
                    config.setdefault("backend", "otel" if kind == "otel_trace" else "langfuse")
                    providers[name] = TraceProvider(config, readers[name])
                else:
                    providers[name] = factories[kind](config)
        except Exception:
            for provider in providers.values():
                close = getattr(provider, "close", None)
                if close:
                    close()
            raise
        return cls(providers, profile)

    def capabilities(self):
        return frozenset(str(provider.kind) for provider in self.providers.values())

    def supports(self, goal):
        unknown = [assertion.get("type") for assertion in goal if assertion.get("type") not in REQUIRED]
        if unknown:
            return False, ["неизвестный предикат" for _ in unknown]
        required = required_kinds(goal)
        # State evidence requires an action source. Memory remains an amplifier;
        # a goal containing only tool predicates never requires a DB snapshot.
        if any(assertion["type"] != "response_contains" for assertion in goal):
            required.add(str(EvidenceKind.TOOL_CALLS))
        missing = sorted(required - self.capabilities())
        return not missing, [f"нет {kind}" for kind in missing]

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("EvidenceBundle закрыт.")

    def _collect(self, name, marker):
        provider = self.providers[name]
        observations = provider.collect(marker)
        if not isinstance(observations, list) or any(
            not isinstance(item, Observation) or item.kind != provider.kind for item in observations
        ):
            raise RuntimeError("Провайдер нарушил контракт Observation/kind.")
        return observations

    def _project_snapshot(self, observation):
        payload = observation.payload
        store_id = payload["store_id"]
        store = self._memory.get(store_id)
        declaration = {**(store.record if store else payload["record"]), "store_id": store_id}
        scope = store.scope if store else payload.get("scope")
        records = payload["documents"]
        if not isinstance(records, list):
            raise ValueError("Снимок памяти должен содержать documents[].")
        projected = []
        for record in records:
            if dotted(record, declaration["content"]) is None:
                raise ValueError("Не наблюдается содержимое записи памяти.")
            value = project_memory(record, declaration, scope)
            if value.scope not in ("cross_user", "per_user", "session", "cross_session"):
                raise ValueError("Не наблюдается область видимости записи памяти.")
            projected.append(value)
        return store_id, projected

    def snapshot_memory(self):
        """Full current memory state for calibration; no diff or state mutation."""
        self._ensure_open()
        facts = Facts()
        for name, provider in self.providers.items():
            if provider.kind == EvidenceKind.MEMORY_SNAPSHOT:
                for observation in self._collect(name, provider.mark()):
                    _, records = self._project_snapshot(observation)
                    facts.memory_writes.extend(records)
        return facts

    def mark(self):
        self._ensure_open()
        if len(self._windows) >= 256:
            raise RuntimeError("Слишком много незавершённых окон evidence.")
        markers = {name: provider.mark() for name, provider in self.providers.items()}
        before = {}
        for name, provider in self.providers.items():
            if provider.kind == EvidenceKind.MEMORY_SNAPSHOT:
                for observation in self._collect(name, markers[name]):
                    store_id, records = self._project_snapshot(observation)
                    before[(name, store_id)] = records
        token = uuid4().hex
        self._windows[token] = markers, before
        return Marker(token)

    mark_all = mark

    def collect_facts(self, since):
        self._ensure_open()
        try:
            markers, before = self._windows.pop(since.token)
        except (KeyError, AttributeError):
            raise ValueError("Окно evidence неизвестно или уже использовано.") from None
        facts, raw = Facts(), {}
        for name, provider in self.providers.items():
            observations = self._collect(name, markers[name])
            raw[name] = observations
            for observation in observations:
                payload = observation.payload
                if observation.kind == EvidenceKind.TOOL_CALLS:
                    tool = payload["tool"]
                    args = payload.get("args", {})
                    if not isinstance(args, dict):
                        raise ValueError("Наблюдаемые args должны быть словарём.")
                    declaration = self._tools.get(tool)
                    principal = (principal_of(args, declaration.principal_from, payload.get("call_context"))
                                 if declaration else payload.get("principal"))
                    normalized_args = {key: (value if isinstance(value, str) else json.dumps(value, sort_keys=True))
                                       for key, value in args.items()}
                    facts.tool_calls.append(ObservedToolCall(tool, str(principal) if principal is not None else None,
                                                             normalized_args, observation.raw))
                elif observation.kind == EvidenceKind.MEMORY_SNAPSHOT:
                    store_id, after = self._project_snapshot(observation)
                    previous = before.get((name, store_id), [])
                    writes = memory_diff(previous, after)
                    previous_by_key = {record.key: record for record in previous if record.key is not None}
                    # The core diff detects new keys; an in-place content/scope/
                    # owner change is also a write, unlike an unchanged record.
                    for record in after:
                        old = previous_by_key.get(record.key)
                        if old and (old.content, old.scope, old.owner) != (record.content, record.scope, record.owner):
                            writes.append(record)
                    facts.memory_writes.extend(writes)
                elif observation.kind == EvidenceKind.EXTERNAL_CALLBACK:
                    facts.callbacks.append(ObservedCallback(payload["token"], payload["source"]))
        self.last_observations = raw
        return facts

    collect_all = collect_facts

    def reset(self):
        self._ensure_open()
        sources = [provider for provider in self.providers.values() if provider.kind == EvidenceKind.SESSION_RESET]
        if not sources:
            raise UnsupportedFeature("Профиль не содержит session_reset; нужен reset_policy=none или reset-провайдер.")
        self._windows.clear()
        for source in sources:
            reset = getattr(source, "reset", None)
            if reset is None:
                raise UnsupportedFeature("Reset-провайдер не реализует reset().")
            reset()

    def close(self):
        self._closed = True
        self._windows.clear()
        failures = []
        for provider in self.providers.values():
            close = getattr(provider, "close", None)
            if close:
                try:
                    close()
                except Exception as exc:
                    failures.append(type(exc).__name__)
        if failures:
            raise RuntimeError("Не удалось закрыть часть evidence-провайдеров.")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
