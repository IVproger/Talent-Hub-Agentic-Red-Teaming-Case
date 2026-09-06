"""Desktop Streamlit control room for state-based agent security scenarios."""
from __future__ import annotations

import hashlib
import html
import json
import os
import sys
import tempfile
import urllib.parse
from dataclasses import asdict
from pathlib import Path

import streamlit as st
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentic_redteam.doctor import run_checks  # noqa: E402
from agentic_redteam.llm import LLMRequestError, LLMRoleConfig, role_configs_from_mapping  # noqa: E402
from agentic_redteam.pipeline import (  # noqa: E402
    DEFAULT_RUNS_ROOT,
    GENERATED_BAC_SCENARIO_ID,
    PipelineRunError,
    RunConfig,
    RunResult,
    sanitize_error,
    run_pipeline,
)
from agentic_redteam.run_storage import RunStorage  # noqa: E402
from agentic_redteam.scenario import bundled_scenarios  # noqa: E402


TARGET_CONFIG = REPO_ROOT / "config" / "target.yaml"
ROLE_LABELS = {
    "attack_generator": "Генератор атак",
    "target_agent": "Целевой ReAct-агент",
    "report_writer": "Автор отчёта",
}


def _write_context_file(text: str, suffix: str) -> Path:
    """Persist edited/uploaded target context to a temp file the pipeline can read."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=suffix, delete=False, encoding="utf-8"
    )
    handle.write(text)
    handle.close()
    return Path(handle.name)


def main() -> None:
    st.set_page_config(
        page_title="Agentic Red Team",
        page_icon="■",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _styles()
    _init_state()
    _page_header()

    try:
        defaults = _load_defaults()
        target_runtime_config = _target_runtime_config()
        catalog = _scenario_catalog()
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        st.error(f"Не удалось загрузить конфигурацию: {sanitize_error(exc)}")
        _render_history()
        return

    with st.sidebar:
        st.markdown("## Настройки")
        st.markdown("### Сценарий")
        scenario_id = st.selectbox(
            "Сценарий",
            tuple(catalog),
            format_func=lambda value: catalog[value]["name"],
            label_visibility="collapsed",
            help="Фиксированные сценарии воспроизводят конкретную цепочку; Adaptive BAC генерирует новые payloads.",
        )
        scenario_meta = catalog[scenario_id]
        st.markdown(_scenario_card_html(scenario_meta), unsafe_allow_html=True)

        with st.form("run-config", clear_on_submit=False):
            st.markdown("### Запуск")
            identity_a, identity_b = st.columns(2)
            with identity_a:
                attacker = st.text_input("CUS атакующего", value="1001")
            with identity_b:
                victim = st.text_input("CUS цели", value="1002")
            attempts = st.number_input(
                "Количество попыток"
                if scenario_id == GENERATED_BAC_SCENARIO_ID
                else "Количество прогонов",
                min_value=1,
                max_value=100,
                value=5,
                step=1,
            )
            auth_mode = st.selectbox(
                "Режим авторизации",
                ("vulnerable", "protected"),
                index=0,
                help="protected проверяет серверную блокировку той же цепочки.",
            )

            selected = defaults
            with st.expander("Модели из конфигурации"):
                st.markdown(_configured_models_html(selected), unsafe_allow_html=True)

            context_error = (
                st.session_state.arch_error or st.session_state.card_error
            )
            with st.expander("Контекст цели", expanded=context_error):
                st.caption(
                    "Схема архитектуры и описание компонентов подаются генератору "
                    "Adaptive BAC. Загрузите файл или вставьте текст."
                )
                arch_upload = st.file_uploader(
                    "Архитектура стенда (.mmd)",
                    type=["mmd", "md", "txt"],
                    key="arch_upload",
                )
                arch_context = st.text_area("Архитектура", height=180)
                if st.session_state.arch_error:
                    st.error("Загрузите файл или вставьте схему архитектуры.")
                card_upload = st.file_uploader(
                    "Описание компонентов (system card)",
                    type=["md", "txt"],
                    key="card_upload",
                )
                card_context = st.text_area("Описание компонентов", height=180)
                if st.session_state.card_error:
                    st.error("Загрузите файл или вставьте описание компонентов.")

            provider_roles = (
                ("attack_generator", "report_writer")
                if scenario_id == GENERATED_BAC_SCENARIO_ID
                else ("report_writer",)
            )
            missing_keys = sorted(
                {
                    selected[role].normalized().api_key_env or "OPENROUTER_API_KEY"
                    for role in provider_roles
                    if selected[role].provider == "openrouter"
                    and not os.environ.get(
                        selected[role].normalized().api_key_env or "OPENROUTER_API_KEY"
                    )
                }
            )
            invalid_identity = (
                attacker.strip() == victim.strip()
                or not attacker.strip().isdecimal()
                or not victim.strip().isdecimal()
            )
            fingerprint = _config_fingerprint(
                selected,
                attacker,
                victim,
                int(attempts),
                auth_mode,
                scenario_id=scenario_id,
                target_context=target_runtime_config,
            )
            readiness_current = (
                st.session_state.environment_fingerprint == fingerprint
                and st.session_state.environment_checks
                and checks_ok_from_dicts(st.session_state.environment_checks)
            )
            if invalid_identity:
                st.error("CUS должны состоять из цифр и различаться.")
            if missing_keys:
                st.error("Настройте ключи: " + ", ".join(missing_keys) + ".")
            if not readiness_current:
                st.caption("Сначала выполните проверку конфигурации.")

            check_col, run_col = st.columns(2)
            with check_col:
                check_submitted = st.form_submit_button("ПРОВЕРИТЬ", width="stretch")
            with run_col:
                submitted = st.form_submit_button(
                    "ЗАПУСТИТЬ",
                    type="primary",
                    width="stretch",
                    disabled=invalid_identity or bool(missing_keys) or not readiness_current,
                )

        if check_submitted:
            st.session_state.run_error = None
            try:
                with st.spinner("Проверяем стенд и провайдеры…"):
                    checks = [
                        item.to_dict()
                        for item in run_checks(
                            selected,
                            provider_roles=provider_roles,
                            **_doctor_target_args(target_runtime_config),
                        )
                    ]
            except Exception as exc:
                checks = [{"name": "preflight", "ok": False, "message": sanitize_error(exc), "blocking": True}]
            st.session_state.environment_checks = checks
            st.session_state.environment_fingerprint = fingerprint
            st.rerun()
        _render_preflight_checks(st.session_state.get("environment_checks", []))

    _render_scenario_summary(scenario_meta)
    progress = st.empty()
    live_trace = st.empty()
    status = st.empty()
    if submitted and not readiness_current:
        st.session_state.run_error = "Конфигурация изменилась. Выполните preflight ещё раз."
        submitted = False
    if submitted:
        context_required = scenario_id == GENERATED_BAC_SCENARIO_ID
        arch_content = (
            arch_upload.getvalue().decode("utf-8", "replace")
            if arch_upload is not None
            else arch_context
        ).strip()
        card_content = (
            card_upload.getvalue().decode("utf-8", "replace")
            if card_upload is not None
            else card_context
        ).strip()
        st.session_state.arch_error = context_required and not arch_content
        st.session_state.card_error = context_required and not card_content
        if st.session_state.arch_error or st.session_state.card_error:
            submitted = False
            st.rerun()
    if submitted and not st.session_state.run_in_progress:
        st.session_state.run_in_progress = True
        st.session_state.run_error = None
        st.session_state.last_run_dir = None
        st.session_state.last_result = None
        bar = progress.progress(0, text="Подготавливаем запуск…")
        live_events: list[dict] = []

        def on_event(event) -> None:
            if event.stage == "completed":
                value = 1.0
            elif event.stage == "report":
                value = 0.95
            elif event.total and event.attempt:
                value = min((event.attempt - 0.1) / event.total, 0.9)
            else:
                value = 0.05
            bar.progress(value, text=event.message)
            live_events.append({"stage": event.stage, "message": event.message, "verdict": event.data.get("verdict")})
            live_trace.markdown(_live_progress_html(live_events), unsafe_allow_html=True)

        # Materialize the target context the user provided; empty fields on a
        # scripted scenario fall back to the bundled RunConfig defaults.
        context_overrides: dict[str, Path] = {}
        context_temp_paths: list[Path] = []
        for content, field, suffix in (
            (arch_content, "arch", ".mmd"),
            (card_content, "system_card", ".md"),
        ):
            if content:
                written = _write_context_file(content, suffix)
                context_overrides[field] = written
                context_temp_paths.append(written)
        try:
            config = RunConfig(
                target_config=TARGET_CONFIG,
                **context_overrides,
                output_root=DEFAULT_RUNS_ROOT,
                num_candidates=int(attempts),
                attacker_cus=attacker.strip(),
                victim_cus=victim.strip(),
                auth_mode=auth_mode,
                llm_roles=selected,
                verify_target_model=True,
                scenario_id=scenario_id,
            )
            result = run_pipeline(config, on_event=on_event)
            st.session_state.last_run_dir = result.run_dir
            st.session_state.last_result = asdict(result)
            status.success(f"Готово · {result.run_id}")
        except (PipelineRunError, LLMRequestError) as exc:
            partial = getattr(exc, "result", None)
            if partial:
                st.session_state.last_run_dir = partial.run_dir
                st.session_state.last_result = asdict(partial)
            st.session_state.run_error = sanitize_error(exc)
        except Exception as exc:
            st.session_state.run_error = sanitize_error(exc)
        finally:
            st.session_state.run_in_progress = False
            for path in context_temp_paths:
                try:
                    path.unlink()
                except OSError:
                    pass

    if st.session_state.run_error:
        st.error(st.session_state.run_error)
    _render_overview(scenario_meta)
    _render_history()


def _page_header() -> None:
    st.markdown(
        """
        <header class="page-head">
          <h1>Agentic Red Team</h1>
          <p>Сценарии безопасности агента с проверкой по состоянию.</p>
        </header>
        """,
        unsafe_allow_html=True,
    )


def _scenario_catalog() -> dict[str, dict]:
    catalog = {
        GENERATED_BAC_SCENARIO_ID: {
            "id": GENERATED_BAC_SCENARIO_ID,
            "name": "Adaptive BAC / Tool Argument",
            "attack_class": "tool_argument_bac",
            "atlas": ["AML.T0012", "AML.T0077"],
            "description": "LLM генерирует вариативные запросы; успех фиксируется только по cross-CUS аргументу реального tool call.",
            "steps": ["generate", "probe", "observe", "verdict"],
            "mode": "generated",
        }
    }
    for scenario in bundled_scenarios().values():
        catalog[scenario.id] = {
            "id": scenario.id,
            "name": scenario.name,
            "attack_class": scenario.attack_class,
            "atlas": list(scenario.atlas),
            "description": scenario.description.strip(),
            "steps": [str(step["name"]) for step in scenario.steps],
            "mode": "scripted",
        }
    return catalog


def _scenario_card_html(meta: dict) -> str:
    atlas = " · ".join(_safe(item) for item in meta.get("atlas", [])) or "NO ATLAS"
    return (
        '<div class="scenario-meta">'
        f'<code>{_safe(meta.get("attack_class", "unknown"))}</code>'
        f'<span>{atlas}</span></div>'
    )


def _render_scenario_summary(meta: dict) -> None:
    steps = '<i>→</i>'.join(f'<span>{_safe(step)}</span>' for step in meta.get("steps", []))
    atlas = " · ".join(_safe(item) for item in meta.get("atlas", [])) or "—"
    st.markdown(
        '<section class="scenario-summary"><div class="scenario-title">'
        f'<h2>{_safe(meta.get("name", "Unknown scenario"))}</h2>'
        f'<code>{_safe(meta.get("id", "unknown"))}</code></div>'
        f'<p>{_safe(meta.get("description", ""))}</p>'
        f'<div class="step-line">{steps}</div>'
        f'<small>{_safe(meta.get("attack_class", "unknown"))} · {atlas}</small></section>',
        unsafe_allow_html=True,
    )


def _render_preflight_checks(checks: list[dict]) -> None:
    if not checks:
        return
    passed = sum(bool(check.get("ok")) for check in checks)
    ready = checks_ok_from_dicts(checks)
    with st.expander(f"Проверка · {passed}/{len(checks)}", expanded=not ready):
        for check in checks:
            marker = "PASS" if check.get("ok") else "FAIL"
            st.markdown(
                '<div class="check-row">'
                f'<b>{marker}</b><span><strong>{_safe(check.get("name", "check"))}</strong>'
                f'<small>{_safe(check.get("message", ""))}</small></span></div>',
                unsafe_allow_html=True,
            )


def _configured_models_html(selected: dict[str, LLMRoleConfig]) -> str:
    rows = []
    for role, label in ROLE_LABELS.items():
        config = selected[role].normalized()
        rows.append(
            '<div class="model-row">'
            f'<span>{_safe(label)}</span>'
            f'<strong>{_safe(config.provider)} / {_safe(config.model)}</strong></div>'
        )
    return (
        '<div class="config-source"><small>config/target.yaml</small>'
        + "".join(rows)
        + "</div>"
    )


def _live_progress_html(events: list[dict]) -> str:
    rows = []
    for event in events[-6:]:
        verdict = event.get("verdict")
        suffix = f" / {str(verdict).upper()}" if verdict else ""
        rows.append(
            '<div class="live-row">'
            f'<code>{_safe(str(event.get("stage", "event")).upper())}{_safe(suffix)}</code>'
            f'<span>{_safe(event.get("message", ""))}</span></div>'
        )
    return '<section class="live-log">' + "".join(rows) + "</section>"


def _render_overview(selected_meta: dict) -> None:
    data = st.session_state.last_result
    if not data:
        st.info("Проверьте конфигурацию и запустите сценарий.")
        return
    if not isinstance(data, dict):
        st.error("Сохранённый результат имеет неверный формат.")
        return
    attempts = _valid_dict_list(data.get("attempts"))
    outcome_tab, trace_tab, report_tab, files_tab = st.tabs(("РЕЗУЛЬТАТ", "ТРЕЙС", "ОТЧЁТ", "ФАЙЛЫ"))
    with outcome_tab:
        _render_outcome_summary(data, attempts, selected_meta)
    with trace_tab:
        _render_trace(attempts)
    with report_tab:
        _render_report(data)
    with files_tab:
        _render_artifacts(data)


def _render_outcome_summary(data: dict, attempts: list[dict], fallback_meta: dict) -> None:
    scorable = [item for item in attempts if item.get("verdict") in ("proven", "not_proven")]
    proven = sum(item.get("verdict") == "proven" for item in scorable)
    if data.get("status") in ("failed", "interrupted"):
        verdict = "INCOMPLETE"
    elif not scorable:
        verdict = "NOT SCORED"
    elif proven:
        verdict = "COMPROMISED"
    else:
        verdict = "NOT PROVEN"
    meta = {
        "id": data.get("scenario_id") or fallback_meta.get("id"),
        "name": data.get("scenario_name") or fallback_meta.get("name"),
        "attack_class": data.get("attack_class") or fallback_meta.get("attack_class"),
        "atlas": data.get("atlas") or fallback_meta.get("atlas", []),
    }
    asr = _format_asr(data.get("asr_percent"), len(scorable))
    ratio = proven / len(scorable) * 100 if scorable else 0
    evidence_count = sum(len(item.get("tool_calls", [])) for item in attempts)
    assertion_count = sum(len(item.get("assertions", [])) for item in attempts)
    st.markdown(
        '<section class="result-summary">'
        '<div class="result-title"><span>ИТОГ</span>'
        f'<strong>{_safe(verdict)}</strong><small>{_safe(data.get("run_id", "unknown"))}</small></div>'
        '<dl>'
        f'<div><dt>ASR</dt><dd>{_safe(asr)}</dd></div>'
        f'<div><dt>Подтверждено</dt><dd>{proven}/{len(scorable)}</dd></div>'
        f'<div><dt>Evidence</dt><dd>{evidence_count} / {assertion_count}</dd></div>'
        f'<div><dt>Статус</dt><dd>{_safe(str(data.get("status", "unknown")).upper())}</dd></div>'
        '</dl>'
        f'<div class="ratio-track"><i style="width:{ratio:.2f}%"></i></div></section>',
        unsafe_allow_html=True,
    )
    atlas = " · ".join(str(item) for item in meta["atlas"]) or "—"
    st.caption(
        f"CUS {data.get('attacker_cus', '—')} → {data.get('victim_cus', '—')} · "
        f"{meta['attack_class']} · {atlas}"
    )
    if data.get("error"):
        st.error(str(data["error"]))
    trace_url = _safe_trace_url(data.get("langfuse_trace_url"))
    if trace_url:
        st.link_button("ОТКРЫТЬ ТРАССУ", trace_url)
    if data.get("observability_warning"):
        st.warning(str(data["observability_warning"]))


def _render_trace(attempts: list[dict]) -> None:
    if not attempts:
        st.info("Трейс ещё не записан.")
        return
    st.dataframe(
        [{
            "RUN": item.get("attempt", "—"),
            "VERDICT": str(item.get("verdict", "invalid")).upper(),
            "ACTOR": item.get("actor_cus", "—"),
            "TOOLS": len(item.get("tool_calls", [])),
            "ASSERTIONS": len(item.get("assertions", [])),
            "CROSS-CUS": ", ".join(item.get("leaked_cus", [])) or "—",
        } for item in attempts],
        width="stretch",
        hide_index=True,
    )
    labels = [f"RUN {int(item.get('attempt', 0)):02d} / {str(item.get('verdict', 'invalid')).upper()}" for item in attempts]
    selected_label = st.selectbox("Прогон", labels)
    item = attempts[labels.index(selected_label)]
    steps = _valid_dict_list(item.get("steps"))
    st.markdown(_trace_rail_html(steps), unsafe_allow_html=True)
    for index, step in enumerate(steps, start=1):
        with st.expander(f"{index:02d} / {str(step.get('name', 'step')).upper()} / CUS {step.get('actor_cus', '—')}", expanded=index == 1):
            request_col, response_col = st.columns(2)
            with request_col:
                st.markdown("##### Запрос")
                st.code(step.get("request") or "—", language=None)
            with response_col:
                st.markdown("##### Ответ")
                st.code(step.get("response") or "—", language=None)
            tool_calls = _valid_dict_list(step.get("tool_calls"))
            if tool_calls:
                st.markdown("##### Tool calls")
                st.dataframe(tool_calls, width="stretch", hide_index=True)
            policies = step.get("new_global_policies", [])
            if isinstance(policies, list) and policies:
                st.markdown("##### Изменения памяти")
                for policy in policies:
                    st.code(policy, language=None)
            facts = step.get("finalize_facts", [])
            if isinstance(facts, list) and facts:
                st.markdown("##### Finalize facts")
                st.json(facts, expanded=False)
            before, after = step.get("memory_before", {}), step.get("memory_after", {})
            if before or after:
                st.caption("Память · до " + json.dumps(before, ensure_ascii=False) + " · после " + json.dumps(after, ensure_ascii=False))
    assertions = _valid_dict_list(item.get("assertions"))
    if assertions:
        st.markdown("#### Проверки")
        st.dataframe(
            [{"ASSERTION": assertion.get("type", "unknown"), "RESULT": "PASS" if assertion.get("passed") else "FAIL", "EVIDENCE": assertion.get("detail", "—")} for assertion in assertions],
            width="stretch",
            hide_index=True,
        )
    if item.get("error"):
        st.error(f"Прогон не оценён · {item['error']}")


def _trace_rail_html(steps: list[dict]) -> str:
    if not steps:
        return ""
    nodes = []
    for index, step in enumerate(steps, start=1):
        calls = len(step.get("tool_calls", []))
        delta = len(step.get("new_global_policies", []))
        nodes.append(
            '<span class="trace-node">'
            f'<b>{index:02d} {_safe(str(step.get("name", "step")))}</b>'
            f'<small>CUS {_safe(step.get("actor_cus", "—"))} · {calls} tool · {delta} memory Δ</small></span>'
        )
    return '<div class="trace-rail">' + "".join(nodes) + "</div>"


def _render_report(data: dict) -> None:
    run_dir = _run_dir(data)
    if run_dir is None:
        return
    report = run_dir / "report.md"
    if not report.is_file():
        st.info("Отчёт ещё не сформирован.")
        return
    st.markdown(report.read_text(encoding="utf-8"))


def _render_artifacts(data: dict) -> None:
    run_dir = _run_dir(data)
    if run_dir is None:
        return
    artifacts = (
        ("REPORT.MD", "report.md", "text/markdown"),
        ("FINDINGS.JSON", "findings.json", "application/json"),
        ("KNOWLEDGE.JSONL", "knowledge.jsonl", "application/x-ndjson"),
        ("CONFIG.JSON", "config.json", "application/json"),
        ("OBSERVABILITY.JSON", "observability.json", "application/json"),
    )
    columns = st.columns(2)
    for index, (label, filename, mime) in enumerate(artifacts):
        path = run_dir / filename
        if path.is_file():
            with columns[index % 2]:
                st.download_button(label, path.read_bytes(), file_name=f"{data.get('run_id', 'run')}-{filename}", mime=mime, width="stretch")


def _run_dir(data: dict) -> Path | None:
    value = data.get("run_dir")
    if not isinstance(value, str):
        st.warning("Для результата не указан каталог артефактов.")
        return None
    return Path(value)


def _render_history() -> None:
    history = RunStorage(DEFAULT_RUNS_ROOT).list_runs()
    if not history:
        return
    with st.expander(f"История запусков · {len(history)}"):
        st.dataframe(
            [{
                "RUN ID": item.get("run_id"),
                "SCENARIO": item.get("scenario_id", GENERATED_BAC_SCENARIO_ID),
                "STATUS": str(item.get("status", "unknown")).upper(),
                "SCORED": item.get("attempts_scored", 0),
                "ASR": _format_asr(item.get("asr_percent"), item.get("attempts_scored", 0)),
                "UPDATED": item.get("updated_at", "—"),
            } for item in history],
            width="stretch",
            hide_index=True,
        )
        available = [item for item in history if item.get("status") != "invalid" and isinstance(item.get("run_id"), str)]
        if available:
            selected = st.selectbox("Сохранённый запуск", [item["run_id"] for item in available], index=0)
            if st.button("ОТКРЫТЬ", width="stretch"):
                item = next(row for row in available if row["run_id"] == selected)
                run_dir = Path(item["run_dir"])
                try:
                    findings = RunStorage(DEFAULT_RUNS_ROOT).load_json(run_dir, "findings.json")
                    st.session_state.last_result = _saved_result(findings, run_dir)
                    st.session_state.run_error = None
                    st.rerun()
                except (OSError, ValueError, TypeError, KeyError):
                    st.error("Результаты запуска повреждены или не завершены.")


def _init_state() -> None:
    defaults = {
        "run_in_progress": False,
        "run_error": None,
        "last_run_dir": None,
        "last_result": None,
        "environment_checks": [],
        "environment_fingerprint": None,
        "arch_error": False,
        "card_error": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _load_defaults() -> dict[str, LLMRoleConfig]:
    raw = yaml.safe_load(TARGET_CONFIG.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("root document must be a mapping")
    return role_configs_from_mapping(raw.get("llm"))


def _target_runtime_config() -> dict[str, str]:
    contents = TARGET_CONFIG.read_text(encoding="utf-8")
    raw = yaml.safe_load(contents) or {}
    if not isinstance(raw, dict):
        raise ValueError("root document must be a mapping")
    target = raw.get("target")
    if not isinstance(target, dict):
        raise ValueError("target section must be a mapping")
    endpoint, compose_value = target.get("endpoint"), target.get("compose_file")
    if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
        raise ValueError("target.endpoint must start with http:// or https://")
    try:
        endpoint_parts = urllib.parse.urlsplit(endpoint)
        endpoint_port = endpoint_parts.port
    except ValueError as exc:
        raise ValueError("target.endpoint is not a valid URL") from exc
    if not endpoint_parts.hostname or endpoint_port is None and ":" in endpoint_parts.netloc.rsplit("]", 1)[-1] or endpoint_parts.query or endpoint_parts.fragment:
        raise ValueError("target.endpoint must not contain a query or fragment")
    if endpoint_parts.username is not None or endpoint_parts.password is not None:
        raise ValueError("target.endpoint must not contain credentials")
    if not isinstance(compose_value, str) or not compose_value.strip():
        raise ValueError("target.compose_file must be a non-empty path")
    compose = Path(compose_value).expanduser()
    if not compose.is_absolute():
        compose = REPO_ROOT / compose
    return {"target_api": endpoint.rstrip("/"), "compose_file": str(compose.resolve()), "config_sha256": hashlib.sha256(contents.encode("utf-8")).hexdigest()}


def _doctor_target_args(target_config: dict[str, str]) -> dict[str, str]:
    return {"target_api": target_config["target_api"], "compose_file": target_config["compose_file"]}


def _config_fingerprint(
    selected: dict[str, LLMRoleConfig],
    attacker: str,
    victim: str,
    attempts: int,
    auth_mode: str,
    scenario_id: str = GENERATED_BAC_SCENARIO_ID,
    target_context: dict[str, str] | None = None,
) -> str:
    value = {
        "llm": {role: config.safe_dict() for role, config in selected.items()},
        "attacker": attacker.strip(),
        "victim": victim.strip(),
        "attempts": attempts,
        "auth_mode": auth_mode,
        "scenario_id": scenario_id,
        "target": target_context or {},
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def checks_ok_from_dicts(checks: list[dict]) -> bool:
    return all(item.get("ok") or not item.get("blocking", True) for item in checks)


def _format_asr(value: object, attempts_scored: object) -> str:
    try:
        scored, percent = int(attempts_scored), float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{percent:.0f}%" if scored > 0 else "N/A"


def _valid_dict_list(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _saved_result(findings: object, run_dir: Path) -> dict:
    if not isinstance(findings, dict):
        raise ValueError("findings.json must contain an object")
    attempts = findings.get("attempts", [])
    if not isinstance(attempts, list) or any(not isinstance(item, dict) for item in attempts):
        raise ValueError("findings attempts must be a list of objects")
    for attempt in attempts:
        for key in ("tool_calls", "steps", "assertions"):
            value = attempt.get(key, [])
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                raise ValueError(f"attempt {key} must be a list of objects")
    required = ("run_id", "status", "attacker_cus", "victim_cus")
    if any(not isinstance(findings.get(key), str) for key in required):
        raise ValueError("findings.json is missing required string fields")
    float(findings.get("asr_percent", 0))
    result = {
        "run_id": findings["run_id"],
        "status": findings["status"],
        "run_dir": str(run_dir),
        "attacker_cus": findings["attacker_cus"],
        "victim_cus": findings["victim_cus"],
        "attempts": attempts,
        "asr_percent": findings.get("asr_percent", 0),
        "error": findings.get("error"),
        "scenario_id": findings.get("scenario_id", GENERATED_BAC_SCENARIO_ID),
        "scenario_name": findings.get("scenario_name", "Generated BAC probe"),
        "attack_class": findings.get("attack", "tool_argument_bac"),
        "atlas": findings.get("atlas", []),
        "description": findings.get("description", ""),
        "langfuse_trace_id": findings.get("langfuse_trace_id"),
        "langfuse_trace_url": findings.get("langfuse_trace_url"),
        "observability_warning": findings.get("observability_warning"),
    }
    observability_path = run_dir / "observability.json"
    if observability_path.is_file():
        try:
            observability = json.loads(observability_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            observability = None
        if isinstance(observability, dict):
            result["langfuse_trace_id"] = observability.get("langfuse_trace_id")
            result["langfuse_trace_url"] = observability.get("langfuse_trace_url")
            result["observability_warning"] = observability.get("warning")
    return result


def _safe_trace_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return value


def _safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def _styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        :root { --ink:#11110f; --paper:#f4f4ef; --surface:#e9e9e4; --line:#a9a9a1; --muted:#5c5c57; }
        html, body, .stApp, button, input, textarea, select { font-family:"JetBrains Mono","SFMono-Regular",Consolas,monospace !important; font-variant-ligatures:none; }
        .material-symbols-rounded,.material-symbols-outlined,[data-testid="stIconMaterial"] { font-family:"Material Symbols Rounded" !important; font-weight:normal !important; font-style:normal !important; letter-spacing:normal !important; text-transform:none !important; white-space:nowrap; word-wrap:normal; direction:ltr; font-feature-settings:"liga"; -webkit-font-feature-settings:"liga"; -webkit-font-smoothing:antialiased; }
        .stApp { background:var(--paper); color:var(--ink); }
        .block-container { max-width:1180px; padding:2rem 3rem 5rem; }
        [data-testid="stHeader"] { background:transparent; }
        [data-testid="stExpandSidebarButton"] { position:fixed!important; top:.75rem!important; left:.75rem!important; z-index:10000!important; margin:0!important; transform:none!important; }
        [data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--line); min-width:360px; max-width:360px; }
        [data-testid="stSidebar"] .block-container { padding:1.5rem 1.25rem 3rem; }
        h1,h2,h3,h4,h5 { color:var(--ink); letter-spacing:-.035em; }
        h2 { font-size:1.15rem !important; }
        h3 { font-size:.72rem !important; letter-spacing:.08em; text-transform:uppercase; margin-top:1.4rem !important; }
        h5 { font-size:.72rem !important; margin-bottom:.45rem !important; }
        p,label { line-height:1.5; } code { color:var(--ink) !important; }
        .page-head { display:flex; align-items:baseline; justify-content:space-between; gap:2rem; border-bottom:1px solid var(--ink); padding:.35rem 0 1rem; margin-bottom:2rem; }
        .page-head h1 { font-size:1.35rem; line-height:1; margin:0; font-weight:700; }
        .page-head p { color:var(--muted); font-size:.72rem; margin:0; }
        .scenario-meta { display:flex; justify-content:space-between; gap:1rem; margin:.65rem 0 .8rem; color:var(--muted); font-size:.64rem; }
        .scenario-meta code { font-size:.64rem; font-weight:600; }
        .scenario-meta span { text-align:right; }
        .config-source>small { display:block; color:var(--muted); font-size:.6rem; padding:0 0 .5rem; }
        .model-row { border-top:1px solid var(--line); padding:.55rem 0; font-size:.62rem; }
        .model-row span { display:block; color:var(--muted); margin-bottom:.2rem; }
        .model-row strong { display:block; overflow-wrap:anywhere; }
        .scenario-summary { margin:0 0 2rem; }
        .scenario-title { display:flex; align-items:baseline; justify-content:space-between; gap:2rem; }
        .scenario-title h2 { font-size:1.4rem !important; margin:0 0 .55rem; }
        .scenario-title code { color:var(--muted) !important; font-size:.65rem; }
        .scenario-summary>p { max-width:76ch; color:var(--muted); font-size:.78rem; margin:0 0 1rem; }
        .scenario-summary>small { display:block; color:var(--muted); font-size:.62rem; margin-top:.65rem; }
        .step-line { display:flex; align-items:center; flex-wrap:wrap; gap:.65rem; border-top:1px solid var(--line); border-bottom:1px solid var(--line); padding:.7rem 0; font-size:.7rem; }
        .step-line span { font-weight:600; }
        .step-line i { color:var(--muted); font-style:normal; }
        .result-summary { border:1px solid var(--ink); margin:1.25rem 0 1rem; }
        .result-title { display:flex; align-items:baseline; gap:1rem; padding:1.15rem 1.25rem; border-bottom:1px solid var(--ink); }
        .result-title span,.result-title small { color:var(--muted); font-size:.64rem; }
        .result-title strong { font-size:1.5rem; margin-right:auto; letter-spacing:-.05em; }
        .result-summary dl { display:grid; grid-template-columns:repeat(4,1fr); margin:0; }
        .result-summary dl>div { padding:.9rem 1rem; border-right:1px solid var(--line); }
        .result-summary dl>div:last-child { border-right:0; }
        .result-summary dt { color:var(--muted); font-size:.61rem; margin-bottom:.4rem; }
        .result-summary dd { font-size:.9rem; font-weight:700; margin:0; }
        .ratio-track { height:.35rem; border-top:1px solid var(--line); }
        .ratio-track i { height:100%; display:block; background:var(--ink); }
        .trace-rail { display:flex; flex-wrap:wrap; gap:.5rem; border-bottom:1px solid var(--line); padding:1rem 0; margin:.5rem 0 1rem; }
        .trace-node { display:flex; gap:.55rem; align-items:baseline; border-right:1px solid var(--line); padding-right:.7rem; }
        .trace-node:last-child { border-right:0; }
        .trace-node b { font-size:.66rem; }
        .trace-node small { color:var(--muted); font-size:.6rem; }
        .live-log { border-bottom:1px solid var(--line); padding:.45rem 0; margin:.5rem 0 1.5rem; }
        .live-row { display:grid; grid-template-columns:10rem 1fr; gap:1rem; padding:.3rem 0; font-size:.66rem; }
        .live-row code { font-weight:700; }
        .check-row { display:grid; grid-template-columns:3.2rem 1fr; border-top:1px solid var(--line); padding:.5rem 0; font-size:.64rem; }
        .check-row:first-child { border-top:0; }
        .check-row span { display:flex; flex-direction:column; gap:.18rem; }
        .check-row strong { font-size:.64rem; }
        .check-row small { color:var(--muted); font-size:.59rem; line-height:1.4; }
        [data-testid="stAlert"],.stAlertContainer { background:var(--surface)!important; color:var(--ink)!important; border-radius:0; }
        [data-testid="stAlert"] { border:1px solid var(--line); }
        [data-testid="stAlert"] *,.stAlertContainer * { color:var(--ink)!important; }
        [data-testid="stAlert"] svg,.stAlertContainer svg { color:var(--ink)!important; fill:var(--ink)!important; }
        a,a:visited,a:hover,a:active,a * { color:var(--ink)!important; }
        a svg,a path,a line { color:var(--ink)!important; stroke:var(--ink)!important; }
        [data-testid="stExpander"] { border:1px solid var(--line); border-radius:0; background:transparent; }
        [data-testid="stCode"] { border-radius:0; border:1px solid var(--line); }
        .stButton>button,.stDownloadButton>button,.stFormSubmitButton>button { border-radius:0!important; border:1px solid var(--ink)!important; background:var(--paper)!important; color:var(--ink)!important; min-height:2.5rem; font-size:.7rem; font-weight:700; letter-spacing:.04em; }
        .stButton>button:hover,.stDownloadButton>button:hover,.stFormSubmitButton>button:hover,.stFormSubmitButton>button[kind="primary"] { background:var(--ink)!important; color:var(--paper)!important; }
        .stFormSubmitButton>button:disabled { background:var(--surface)!important; color:var(--muted)!important; border-color:var(--line)!important; }
        [data-baseweb="select"]>div,[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input { border-radius:0!important; border-color:var(--line)!important; background:var(--paper)!important; }
        [data-baseweb="tab-list"] { border-bottom:1px solid var(--line); gap:1.1rem; }
        [data-baseweb="tab"] { border-radius:0; padding:.7rem 0; font-size:.68rem; }
        [aria-selected="true"][role="tab"] { color:var(--ink); border-bottom:2px solid var(--ink); }
        [data-testid="stDataFrame"] { border:1px solid var(--line); }
        [data-testid="stProgressBar"]>div>div { background:var(--ink)!important; }
        hr { border-color:var(--line); }
        @media (prefers-reduced-motion:reduce) { *,*::before,*::after { transition-duration:.01ms!important; animation-duration:.01ms!important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
