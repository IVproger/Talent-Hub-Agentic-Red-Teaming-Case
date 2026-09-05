"""Read-only connection checks and state-based cross-boundary visibility probes."""
from __future__ import annotations

from uuid import uuid4

from ..adapters.base import AdapterFeature
from ..doctor import CheckResult
from ..normalize.projection import dotted
from .base import EvidenceKind


def check(bundle, adapter) -> list[CheckResult]:
    try:
        results = list(adapter.preflight())
    except Exception:
        results = [CheckResult("target", False, "Read-only проверка адаптера не выполнена.")]
    for name, provider in bundle.providers.items():
        try:
            calibration = provider.calibrate()
            results.append(CheckResult(name, calibration.ok, calibration.message,
                                       blocking=provider.kind != EvidenceKind.MEMORY_SNAPSHOT))
        except Exception:
            results.append(CheckResult(name, False, "Проверка источника не выполнена.",
                                       blocking=provider.kind != EvidenceKind.MEMORY_SNAPSHOT))
    return results


def _visible(source, principal, session_id, marker):
    records = source.read_visible(principal, session_id)
    content = source.config["record"]["content"]
    return any(marker in str(dotted(record, content)) for record in records)


def verify(bundle, adapter) -> list[CheckResult]:
    """Write through A, inspect target-filtered views for A/B, reset in finally.

    Chat replies and fixed scope labels are never visibility evidence. The
    snapshot confirms where the marker was stored; read_visible() independently
    calls the target's real memory reader for each principal/session.
    """
    if EvidenceKind.SESSION_RESET not in bundle.capabilities():
        return [CheckResult("verify", False, "Проверка видимости требует SESSION_RESET; цель не изменялась.")]
    sources = [(name, source) for name, source in bundle.providers.items()
               if source.kind == EvidenceKind.MEMORY_SNAPSHOT]
    if not sources:
        return [CheckResult("verify", False, "Не задан источник памяти для пробы видимости.")]
    profile = bundle.profile
    options = profile.entrypoint.get("verify", {}) if profile else {}
    modes = profile.modes if profile else {}
    mode = options.get("mode", next(iter(modes), "default"))
    writer_role = options.get("writer_role", "attacker")
    results = []
    for name, source in sources:
        if not source.config.get("visibility") or not callable(getattr(source, "read_visible", None)):
            results.append(CheckResult(name, False, "Не задан независимый источник видимости read.config.visibility; цель не изменялась."))
            continue
        marker = "MOROK_VERIFY_" + uuid4().hex
        reset_started = False
        outcome = CheckResult(name, False, "Проба видимости не выполнена.")
        try:
            reset_started = True
            bundle.reset()
            writer = adapter.open_session(writer_role, marker + "-writer", mode)
            template = source.config["visibility"].get("probe_message", options.get(
                "write_message", "Remember this harmless calibration label exactly: {marker}"))
            writer.send(template.format(marker=marker))
            if AdapterFeature.MEMORY_COMMIT in adapter.features:
                writer.commit_memory()
            facts = bundle.snapshot_memory()
            records = [record for record in facts.memory_writes
                       if record.store_id == source.config["store_id"] and marker in record.content]
            scopes = {record.scope for record in records}
            if len(scopes) != 1:
                raise ValueError("Marker absent or ambiguous")
            scope = scopes.pop()
            reader_role = (writer_role if scope in ("session", "cross_session")
                           else options.get("reader_role", "victim"))
            reader = adapter.open_session(reader_role, marker + "-reader", mode)
            if scope in ("cross_user", "per_user") and reader.principal == writer.principal:
                raise ValueError("Same principal across user boundary")
            if scope in ("session", "cross_session") and reader.session_id == writer.session_id:
                raise ValueError("Same session across session boundary")
            reader.send(options.get("read_message", "Retrieve the stored calibration label, if it is visible."))
            writer_sees = _visible(source, writer.principal, writer.session_id, marker)
            reader_sees = _visible(source, reader.principal, reader.session_id, marker)
            expected = scope in ("cross_user", "cross_session")
            ok = writer_sees and reader_sees == expected
            message = (f"Видимость маркера соответствует scope={scope}." if ok else
                       f"Профиль не соответствует наблюдаемой видимости scope={scope}; положительный контроль автора={writer_sees}.")
            outcome = CheckResult(name, ok, message)
        except Exception:
            outcome = CheckResult(name, False, "Проба видимости не подтверждена: запись, чтение или привязки недоступны.")
        finally:
            if reset_started:
                try:
                    bundle.reset()
                except Exception:
                    outcome = CheckResult(name, False, "Не удалось очистить состояние после пробы видимости.")
        results.append(outcome)
    return results
