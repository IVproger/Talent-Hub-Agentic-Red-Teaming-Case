"""Streamlit-демо поверх профиля и кампании.

Своей логики нет: экран собирает кампанию теми же функциями, что и CLI, и
рендерит артефакты прогона. Provider/model — read-only из YAML.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentic_redteam.adapters.http_chat import HttpChatAdapter  # noqa: E402
from agentic_redteam.app_cli import (  # noqa: E402
    PROFILES_ROOT,
    _config_mapping,
    coverage_of,
    execute_campaign,
    load_profile,
    new_run_id,
    preview_scenario,
    profile_principals,
    reporter_from_config,
    surface_of,
)
from agentic_redteam.campaign.authorization import authorization_from_mapping  # noqa: E402
from agentic_redteam.campaign.scenarios import resolve as resolve_specs  # noqa: E402
from agentic_redteam.evidence.bundle import EvidenceBundle  # noqa: E402
from agentic_redteam.evidence.calibrate import check  # noqa: E402
from agentic_redteam.profile.registry import ProfileRegistry  # noqa: E402
from agentic_redteam.storage.runs import RunStorage  # noqa: E402

RUNS_ROOT = REPO_ROOT / "runs"
TARGET_CONFIG = REPO_ROOT / "config" / "target.yaml"
REACHABLE_LABEL = {
    "state": "state",
    "text": "text · потолок indirect",
    "unobservable": "нет источника",
}


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

    references = _profile_options()
    if not references:
        st.error(f"В реестре {PROFILES_ROOT} нет профилей.")
        _render_history()
        return

    with st.sidebar:
        st.markdown("## Настройки")
        reference = st.selectbox("Профиль", references, index=0, key="profile_ref")
        try:
            profile = load_profile(reference)
        except Exception as exc:
            st.error(f"Профиль не загрузился: {_safe(str(exc))}")
            _render_history()
            return
        rows, available = coverage_of(profile, [])
        by_id = {row["scenario_id"]: row for row in rows}
        st.caption("Источники: " + (", ".join(sorted(available)) or "—"))

        with st.form("campaign", clear_on_submit=False):
            st.markdown("### Кампания")
            runnable = [row["scenario_id"] for row in rows if row["reachable"] != "unobservable"]
            scenario_ids = st.multiselect(
                "Сценарии",
                [row["scenario_id"] for row in rows],
                default=runnable,
                format_func=lambda value: f"{value} · {REACHABLE_LABEL[by_id[value]['reachable']]}",
                key="campaign_scenarios",
            )
            modes = st.multiselect("Режимы", sorted(profile.modes),
                                   default=sorted(profile.modes), key="campaign_modes")
            trials = st.number_input("Прогонов на payload", min_value=1, max_value=100,
                                     value=1, step=1)
            blocked = sorted(set(scenario_ids) & {row["scenario_id"] for row in rows
                                                  if row["reachable"] == "unobservable"})
            if blocked:
                st.error("Не запустятся — нет источника: " + ", ".join(blocked))
            st.caption("«Проверить» — необязательная диагностика; запуск сам проверит цель.")
            check_col, run_col = st.columns(2)
            with check_col:
                check_submitted = st.form_submit_button("ПРОВЕРИТЬ", width="stretch")
            with run_col:
                submitted = st.form_submit_button(
                    "ЗАПУСТИТЬ", type="primary", width="stretch",
                    disabled=not scenario_ids or bool(blocked),
                )

        if check_submitted:
            st.session_state.run_error = None
            st.session_state.environment_checks = _preflight(profile)
            st.rerun()
        _render_preflight_checks(st.session_state.get("environment_checks", []))

    _render_surface(surface_of(profile))
    planned = _planned(profile, scenario_ids)
    _render_preview(planned)

    progress, live_trace, status = st.empty(), st.empty(), st.empty()
    if submitted and not st.session_state.run_in_progress:
        _start_run(profile, planned, modes, int(trials), progress, live_trace, status)

    if st.session_state.run_error:
        st.error(st.session_state.run_error)
    for note in st.session_state.get("skipped", []):
        st.warning(f"пропущено · {note}")
    _render_results()
    _render_history()


def _profile_options() -> list[str]:
    try:
        return [f"{name}@{version}" for name, version in ProfileRegistry(PROFILES_ROOT).list()]
    except Exception:
        return []


def _planned(profile, scenario_ids: list[str]) -> list:
    if not scenario_ids:
        return []
    try:
        principals = profile_principals(profile)
        return [spec.to_planned(principals) for spec in resolve_specs(list(scenario_ids))]
    except Exception:
        return []


def _preflight(profile) -> list[dict]:
    """Тот же read-only `check`, что и в CLI: цель не меняется."""
    try:
        with EvidenceBundle.from_profile(profile) as bundle:
            adapter = HttpChatAdapter.from_profile(profile)
            try:
                return [item.to_dict() for item in check(bundle, adapter)]
            finally:
                adapter.close()
    except Exception as exc:
        return [{"name": "preflight", "ok": False, "message": str(exc), "blocking": True}]


def _start_run(profile, planned, modes, trials, progress, live_trace, status) -> None:
    st.session_state.run_in_progress = True
    st.session_state.run_error = None
    st.session_state.last_result = None
    st.session_state.skipped = []
    bar = progress.progress(0, text="Готовим кампанию…")
    events: list[dict] = []

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
        events.append({"stage": event.stage, "message": event.message,
                       "verdict": event.data.get("verdict")})
        live_trace.markdown(_live_progress_html(events), unsafe_allow_html=True)

    run_id = new_run_id()
    try:
        summary = execute_campaign(
            profile, planned, modes, trials, RUNS_ROOT, run_id,
            reporter_llm=reporter_from_config(TARGET_CONFIG), on_event=on_event,
            # US-34: демо подчиняется той же рамке, что и CLI.
            authorization=authorization_from_mapping(
                _config_mapping(TARGET_CONFIG)).as_record())
        st.session_state.skipped = summary["skipped"]
        run_dir = Path(summary["run_dir"])
        st.session_state.last_result = _saved_result(
            RunStorage(RUNS_ROOT).load_json(run_dir, "findings.json"), run_dir)
        status.success(f"Готово · {summary['run_id']}")
    except KeyboardInterrupt:
        st.session_state.run_error = "Прогон остановлен; собранное сохранено."
    except Exception as exc:
        st.session_state.run_error = str(exc)
    finally:
        st.session_state.run_in_progress = False


def _render_surface(surface: dict) -> None:
    with st.expander(f"Поверхность цели · {surface['name']}@{surface['version']}"):
        st.caption(f"{surface['adapter']} · {surface['base_url']} · "
                   f"атрибуция {surface['attribution']}")
        columns = st.columns(2)
        with columns[0]:
            st.markdown("##### Инструменты")
            st.dataframe([{
                "TOOL": tool["name"],
                "ARGS": ", ".join(tool["args"]) or "—",
                "SENSITIVE": "да" if tool["sensitive"] else "нет",
                "PRINCIPAL": tool["principal_from"].get("name")
                             or tool["principal_from"].get("kind", "—"),
            } for tool in surface["tools"]], width="stretch", hide_index=True)
            st.markdown("##### Границы изоляции")
            st.dataframe([{"BOUNDARY": item["id"], "ПО": item["principal"],
                           "ОБЕЩАНИЕ": item["claim"]} for item in surface["isolation"]],
                         width="stretch", hide_index=True)
        with columns[1]:
            st.markdown("##### Память")
            st.dataframe([{"STORE": item["id"], "SCOPE": item["scope"],
                           "READER": item["provider"]} for item in surface["memory"]],
                         width="stretch", hide_index=True)
            st.markdown("##### Evidence")
            st.dataframe([{"ID": item["id"], "PROVIDER": item["provider"],
                           "KIND": item["kind"] or "неизвестен"}
                          for item in surface["evidence"]], width="stretch", hide_index=True)
        st.caption("Режимы: " + (", ".join(f"{name} ({scope})" for name, scope
                                           in surface["modes"].items()) or "—"))


def _render_preview(planned: list) -> None:
    if not planned:
        return
    with st.expander(f"Предпросмотр · {len(planned)} сценарий(ев)"):
        st.caption("Ровно это будет отправлено цели — как в `run --dry-run`.")
        for scenario in (preview_scenario(item) for item in planned):
            st.markdown(f"**{scenario['id']}** · {scenario['attack_class']} · "
                        f"{', '.join(scenario['standard_refs']) or '—'}")
            st.caption(f"актор {scenario['actor']} · граница {scenario['boundary'] or '—'}"
                       f" · reset {scenario['reset_policy']}")
            st.dataframe([{
                "#": index, "STEP": step["name"], "ACTOR": step["actor"],
                "ЧТО": {"payload": "← payload", "commit_memory": "← фиксация памяти"}.get(
                    step["kind"], step["message"] or ""),
            } for index, step in enumerate(scenario["steps"], start=1)],
                width="stretch", hide_index=True)
            for index, payload in enumerate(scenario["payloads"], start=1):
                st.code(f"[{index}] {payload}", language=None)
            st.dataframe([{"ПРЕДИКАТ": item.get("type"),
                           "ПАРАМЕТРЫ": ", ".join(f"{k}={v}" for k, v in item.items()
                                                  if k != "type") or "—"}
                          for item in scenario["goal"]], width="stretch", hide_index=True)


def _render_results() -> None:
    data = st.session_state.last_result
    if not data:
        st.info("Выберите сценарии и запустите кампанию.")
        return
    outcome_tab, attempts_tab, report_tab, files_tab = st.tabs(
        ("РЕЗУЛЬТАТ", "ПОПЫТКИ", "ОТЧЁТ", "ФАЙЛЫ"))
    with outcome_tab:
        _render_outcome(data)
    with attempts_tab:
        _render_attempts(data)
    with report_tab:
        _render_report(data)
    with files_tab:
        _render_artifacts(data)


def _render_outcome(data: dict) -> None:
    attempts = _valid_dict_list(data.get("attempts"))
    findings = _valid_dict_list(data.get("findings"))
    scorable = [item for item in attempts if item.get("verdict") in ("proven", "not_proven")]
    proven = sum(item.get("verdict") == "proven" for item in scorable)
    if data.get("status") in ("failed", "interrupted"):
        verdict = "INCOMPLETE"
    elif any(item.get("verdict") == "proven" for item in findings):
        verdict = "COMPROMISED"
    elif any(item.get("verdict") == "indirect" for item in findings):
        verdict = "INDIRECT"
    elif not scorable:
        verdict = "NOT SCORED"
    else:
        verdict = "NOT PROVEN"
    ratio = proven / len(scorable) * 100 if scorable else 0
    st.markdown(
        '<section class="result-summary">'
        '<div class="result-title"><span>ИТОГ</span>'
        f'<strong>{_safe(verdict)}</strong><small>{_safe(data.get("run_id", "unknown"))}</small></div>'
        '<dl>'
        f'<div><dt>ASR</dt><dd>{_safe(_format_asr(data.get("asr_percent"), len(scorable)))}</dd></div>'
        f'<div><dt>Подтверждено</dt><dd>{proven}/{len(scorable)}</dd></div>'
        f'<div><dt>Находок</dt><dd>{len(findings)}</dd></div>'
        f'<div><dt>Статус</dt><dd>{_safe(str(data.get("status", "unknown")).upper())}</dd></div>'
        '</dl>'
        f'<div class="ratio-track"><i style="width:{ratio:.2f}%"></i></div></section>',
        unsafe_allow_html=True,
    )
    st.caption(f"Профиль {data.get('profile', '—')} · режимы "
               f"{', '.join(data.get('modes', [])) or '—'}")
    if findings:
        st.markdown("#### Находки")
        st.dataframe([{
            "SEVERITY": str(item.get("severity", "—")).upper(),
            "СЦЕНАРИЙ": item.get("scenario_id"),
            "ЭТАП": item.get("chain_stage", "—"),
            "VERDICT": str(item.get("verdict", "—")).upper(),
            "ТОЧКА КОМПРОМЕТАЦИИ": item.get("compromise_point", "—"),
            "EVIDENCE": ", ".join(item.get("evidence_refs", [])) or "—",
        } for item in findings], width="stretch", hide_index=True)
    for note in data.get("limitations", []):
        st.caption(f"Ограничение: {note}")


def _render_attempts(data: dict) -> None:
    attempts = _valid_dict_list(data.get("attempts"))
    if not attempts:
        st.info("Попыток не записано.")
        return
    st.dataframe([{
        "#": item.get("attempt"),
        "СЦЕНАРИЙ": item.get("scenario_id"),
        "РЕЖИМ": item.get("mode") or "—",
        "АКТОР": item.get("roles", "—"),
        "VERDICT": str(item.get("verdict", "invalid")).upper(),
        "ПРИЗНАК": item.get("signal", "—"),
    } for item in attempts], width="stretch", hide_index=True)
    run_dir = _run_dir(data)
    if run_dir is None:
        return
    evidence = sorted(run_dir.glob("evidence-*.json"))
    if not evidence:
        st.caption("Evidence-файлов нет: ни одна попытка не собрала фактов.")
        return
    chosen = st.selectbox("Evidence попытки", [path.name for path in evidence],
                          key="evidence_file")
    st.json(json.loads((run_dir / chosen).read_text(encoding="utf-8")), expanded=False)


def _render_artifacts(data: dict) -> None:
    run_dir = _run_dir(data)
    if run_dir is None:
        return
    artifacts = (
        ("REPORT.MD", "report.md", "text/markdown"),
        ("FINDINGS.JSON", "findings.json", "application/json"),
        ("CAMPAIGN.JSON", "campaign.json", "application/json"),
        ("TRANSCRIPT.JSONL", "transcript.jsonl", "application/x-ndjson"),
        ("STATUS.JSON", "status.json", "application/json"),
    )
    columns = st.columns(2)
    for index, (label, filename, mime) in enumerate(artifacts):
        path = run_dir / filename
        if path.is_file():
            with columns[index % 2]:
                st.download_button(label, path.read_bytes(),
                                   file_name=f"{data.get('run_id', 'run')}-{filename}",
                                   mime=mime, width="stretch")


def _render_history() -> None:
    try:
        history = RunStorage(RUNS_ROOT).list_runs()
    except Exception:
        history = []
    if not history:
        return
    with st.expander(f"История запусков · {len(history)}"):
        st.dataframe([{
            "RUN ID": item.get("run_id"),
            "STATUS": str(item.get("status", "unknown")).upper(),
            "ASR": _format_asr(item.get("asr_percent"), 1),
        } for item in history], width="stretch", hide_index=True)
        available = [item for item in history
                     if item.get("status") not in ("invalid", "running")
                     and isinstance(item.get("run_id"), str)]
        if not available:
            return
        selected = st.selectbox("Сохранённый прогон", [item["run_id"] for item in available],
                                key="history_run")
        if st.button("ОТКРЫТЬ", width="stretch"):
            item = next(row for row in available if row["run_id"] == selected)
            run_dir = Path(item["run_dir"])
            try:
                st.session_state.last_result = _saved_result(
                    RunStorage(RUNS_ROOT).load_json(run_dir, "findings.json"), run_dir)
                st.session_state.run_error = None
                st.rerun()
            except (OSError, ValueError, TypeError, KeyError):
                st.error("Результаты прогона повреждены или не завершены.")


def _saved_result(findings: object, run_dir: Path) -> dict:
    if not isinstance(findings, dict):
        raise ValueError("findings.json must contain an object")
    for key in ("attempts", "findings"):
        value = findings.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError(f"findings {key} must be a list of objects")
    if any(not isinstance(findings.get(key), str) for key in ("run_id", "status")):
        raise ValueError("findings.json is missing required string fields")
    float(findings.get("asr_percent", 0))
    return {**findings, "run_dir": str(run_dir)}


def _init_state() -> None:
    defaults = {
        "run_in_progress": False,
        "run_error": None,
        "last_result": None,
        "environment_checks": [],
        "skipped": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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


def _run_dir(data: dict) -> Path | None:
    value = data.get("run_dir")
    if not isinstance(value, str):
        st.warning("Для результата не указан каталог артефактов.")
        return None
    return Path(value)


def _render_report(data: dict) -> None:
    run_dir = _run_dir(data)
    if run_dir is None:
        return
    report = run_dir / "report.md"
    if not report.is_file():
        st.info("Отчёт ещё не сформирован.")
        return
    st.markdown(report.read_text(encoding="utf-8"))


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
        [data-testid="stAlert"] { border:0; }
        [data-testid="stAlert"] *,.stAlertContainer * { color:var(--ink)!important; }
        [data-testid="stAlert"] svg,.stAlertContainer svg { color:var(--ink)!important; fill:var(--ink)!important; }
        a,a:visited,a:hover,a:active,a * { color:var(--ink)!important; }
        a svg,a path,a line { color:var(--ink)!important; stroke:var(--ink)!important; }
        [data-testid="stExpander"] { border:0; border-radius:0; background:transparent; }
        [data-testid="stCode"] { border-radius:0; border:0; }
        .stButton>button,.stDownloadButton>button,.stFormSubmitButton>button { border-radius:0!important; border:1px solid var(--ink)!important; background:var(--paper)!important; color:var(--ink)!important; min-height:2.5rem; font-size:.7rem; font-weight:700; letter-spacing:.04em; }
        .stButton>button:hover,.stDownloadButton>button:hover,.stFormSubmitButton>button:hover,.stFormSubmitButton>button[kind="primary"] { background:var(--ink)!important; color:var(--paper)!important; }
        .stFormSubmitButton>button:disabled { background:var(--surface)!important; color:var(--muted)!important; border-color:var(--line)!important; }
        [data-baseweb="select"]>div,[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input { border-radius:0!important; border-color:var(--line)!important; background:var(--paper)!important; }
        [data-baseweb="tab-list"] { border-bottom:1px solid var(--line); gap:1.1rem; }
        [data-baseweb="tab"] { border-radius:0; padding:.7rem 0; font-size:.68rem; }
        [aria-selected="true"][role="tab"] { color:var(--ink); border-bottom:2px solid var(--ink); }
        [data-testid="stDataFrame"] { border:0; }
        [data-testid="stProgressBar"]>div>div { background:var(--ink)!important; }
        hr { border-color:var(--line); }
        @media (prefers-reduced-motion:reduce) { *,*::before,*::after { transition-duration:.01ms!important; animation-duration:.01ms!important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )





if __name__ == "__main__":
    main()
