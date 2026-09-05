"""Tool evidence from Langfuse or an OTLP JSON export.

Readers share spans_for(trace_id), independent of optional run telemetry.
Langfuse pagination and OTLP decoding follow the official specifications linked
in docs/blueprint/plans/oushtt-evidence-integration.md.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from ...errors import PipelineConfigurationError
from ...normalize.projection import dotted, principal_of
from ..base import CalibrationResult, EvidenceKind, Marker, Observation


class TraceReader(Protocol):
    def spans_for(self, trace_id: str) -> list[dict]: ...


def _http_json(url, headers, timeout=30):
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class LangfuseReader:
    def __init__(self, config, *, get_json=None, environ=None):
        self.config = copy.deepcopy(config)
        self.environ = os.environ if environ is None else environ
        self.get_json = get_json or (lambda url, headers: _http_json(url, headers, config.get("timeout", 30)))
        self.host = config.get("host", "").rstrip("/")
        parts = urlsplit(self.host)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.query or parts.fragment:
            raise PipelineConfigurationError("Langfuse evidence требует корректный host.")
        self.version = int(config.get("api_version", 2))
        if self.version not in (1, 2):
            raise PipelineConfigurationError("Langfuse api_version должен быть 1 или 2.")

    def spans_for(self, trace_id):
        try:
            public = self.environ[self.config["public_key_env"]]
            secret = self.environ[self.config["secret_key_env"]]
            if not public or not secret:
                raise ValueError
            headers = {"Authorization": "Basic " + base64.b64encode(f"{public}:{secret}".encode()).decode()}
            now = datetime.now(UTC)
            params = {"traceId": trace_id, "limit": 100,
                      "fromStartTime": self.config.get("from_start_time", (now - timedelta(seconds=self.config.get("lookback_seconds", 86400))).isoformat()),
                      "toStartTime": self.config.get("to_start_time", (now + timedelta(minutes=1)).isoformat())}
            endpoint = "/api/public/v2/observations" if self.version == 2 else "/api/public/observations"
            if self.version == 2:
                params["fields"] = "core,basic,io,metadata"
            result, seen_cursors = [], set()
            for page in range(1, self.config.get("max_pages", 100) + 1):
                if self.version == 1:
                    params["page"] = page
                payload = self.get_json(self.host + endpoint + "?" + urlencode(params), headers)
                rows = payload["data"]
                if not isinstance(rows, list):
                    raise ValueError
                for row in rows:
                    if row.get("traceId") != trace_id:
                        raise ValueError("Trace mismatch")
                    data = row.get("input")
                    if isinstance(data, str):
                        try:
                            data = json.loads(data)
                        except ValueError:
                            data = {}
                    result.append({"id": row["id"], "trace_id": trace_id, "name": row.get("name", ""),
                                   "attributes": data if isinstance(data, dict) else {},
                                   "metadata": row.get("metadata", {}), "raw": row})
                meta = payload.get("meta", {})
                if self.version == 2:
                    cursor = meta.get("cursor")
                    if not cursor:
                        return result
                    if cursor in seen_cursors:
                        raise ValueError("Repeated cursor")
                    seen_cursors.add(cursor)
                    params["cursor"] = cursor
                elif page >= meta.get("totalPages", page + 1) or len(rows) < params["limit"]:
                    return result
            raise ValueError("Pagination limit exceeded")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise RuntimeError("Не удалось полностью прочитать Langfuse evidence; проверьте доступ, trace-id и пагинацию.") from None


def _any_value(value):
    for kind, convert in (("stringValue", str), ("boolValue", bool), ("intValue", int),
                          ("doubleValue", float), ("bytesValue", str)):
        if kind in value:
            return convert(value[kind])
    if "arrayValue" in value:
        return [_any_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return {item["key"]: _any_value(item["value"]) for item in value["kvlistValue"].get("values", [])}
    return None


class OtelJsonReader:
    """Read collector OTLP JSON/JSONL exports, not the write-only /v1/traces route."""

    def __init__(self, config, *, get_json=None):
        self.config = copy.deepcopy(config)
        self.get_json = get_json or _http_json
        if bool(config.get("path")) == bool(config.get("read_url")):
            raise PipelineConfigurationError("OTLP evidence требует ровно один path или read_url экспорта.")

    def spans_for(self, trace_id):
        try:
            if self.config.get("path"):
                text = Path(self.config["path"]).read_text(encoding="utf-8")
                if not text.strip():
                    return []
                try:
                    batches = [json.loads(text)]
                except ValueError:
                    batches = [json.loads(line) for line in text.splitlines() if line.strip()]
            else:
                batches = [self.get_json(self.config["read_url"], {})]
            result = []
            for batch in batches:
                for resource in batch["resourceSpans"]:
                    for scope in resource["scopeSpans"]:
                        for span in scope["spans"]:
                            if span["traceId"].lower() != trace_id.lower():
                                continue
                            result.append({"id": span["spanId"], "trace_id": span["traceId"],
                                           "name": span["name"], "raw": span,
                                           "attributes": {item["key"]: _any_value(item["value"])
                                                          for item in span.get("attributes", [])}})
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise RuntimeError("Не удалось прочитать корректный OTLP JSON/JSONL экспорт.") from None


def _identity(span):
    return span.get("id") or hashlib.sha256(json.dumps(span, sort_keys=True).encode()).hexdigest()


class TraceProvider:
    kind = EvidenceKind.TOOL_CALLS

    def __init__(self, config, reader=None):
        self.config = copy.deepcopy(config)
        backend = config.get("backend", "langfuse")
        if backend not in ("langfuse", "otel"):
            raise PipelineConfigurationError("Trace backend должен быть langfuse или otel.")
        self.reader = reader if reader is not None else (LangfuseReader(config) if backend == "langfuse" else OtelJsonReader(config))
        self._id = uuid4().hex
        self.trace_id = config.get("trace_id")

    def bind_trace(self, trace_id):
        if not isinstance(trace_id, str) or not trace_id:
            raise ValueError("Не задан trace-id цели.")
        self.trace_id = trace_id

    def _spans(self, trace_id):
        if not trace_id:
            raise RuntimeError("Trace evidence требует trace_id или bind_trace(trace_id) до mark.")
        try:
            spans = self.reader.spans_for(trace_id)
            if not isinstance(spans, list) or any(not isinstance(item, dict) for item in spans):
                raise ValueError
            return spans
        except (OSError, ValueError, TypeError):
            raise RuntimeError("Trace-источник недоступен или вернул некорректные спаны.") from None

    def mark(self):
        spans = self._spans(self.trace_id)
        return Marker(json.dumps({"source": self._id, "trace_id": self.trace_id,
                                  "seen": [_identity(span) for span in spans]}))

    def _observations(self, spans):
        result = []
        prefix = self.config.get("tool_prefix", "tool.")
        for span in spans:
            name = span.get("name", "")
            if not isinstance(name, str) or not prefix or not name.startswith(prefix):
                continue
            try:
                args = dotted(span, self.config.get("args_path", "attributes"))
                context = dotted(span, self.config.get("context_path", "attributes"))
                if not isinstance(args, dict) or not isinstance(context, dict):
                    raise ValueError
                principal = principal_of(args, self.config.get("principal_from", {"kind": "none"}), context)
                payload = {"tool": name[len(prefix):], "args": args, "principal": principal, "call_context": context}
                result.append(Observation(self.kind, payload, json.dumps(span, sort_keys=True)))
            except (ValueError, KeyError, TypeError):
                raise RuntimeError("Спан инструмента не соответствует trace-привязкам профиля.") from None
        return result

    def collect(self, since):
        try:
            marker = json.loads(since.token)
            if marker["source"] != self._id:
                raise ValueError
            seen = set(marker["seen"])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError("Некорректный trace-маркер.") from None
        return self._observations([span for span in self._spans(marker["trace_id"]) if _identity(span) not in seen])

    def calibrate(self):
        try:
            observations = self._observations(self._spans(self.trace_id))
            expected = self.config.get("calibration", {}).get("expected_principal")
            ok = bool(observations) and (expected is None or any(o.payload["principal"] == str(expected) for o in observations))
            return CalibrationResult(ok, "Tool-спаны доступны и соответствуют привязке." if ok else
                                     "Контрольные tool-спаны не найдены.")
        except RuntimeError:
            return CalibrationResult(False, "Trace evidence недоступен или привязка не подтверждена.")
