"""Streamlit UI: документы цели → профиль (LLM-судья) → проверка → OWASP-прогон.

Цель задаётся endpoint'ом и загруженными документами (без захардкоженного
реестра). Сценарии берутся из OWASP, режимы — из профиля; пользователь только
проверяет цель и запускает атаку. Движок — тот же `execute_campaign`, что и CLI.
"""
from __future__ import annotations

import html
import sys
import tempfile
from pathlib import Path

import streamlit as st
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentic_redteam.adapters.http_chat import HttpChatAdapter  # noqa: E402
from agentic_redteam.app_cli import (  # noqa: E402
    _config_mapping,
    _generate_payloads,
    _role_configs_at,
    build_baseline,
    execute_campaign,
    load_profile,
    make_llm_client,
    new_run_id,
    reporter_from_config,
    telemetry_from_config,
)
from agentic_redteam.campaign.authorization import authorization_from_mapping  # noqa: E402
from agentic_redteam.evidence.bundle import EvidenceBundle  # noqa: E402
from agentic_redteam.evidence.calibrate import check  # noqa: E402
from agentic_redteam.profile.ingest import build_draft, read_document  # noqa: E402
from agentic_redteam.profile.schema import TargetProfile  # noqa: E402
from agentic_redteam.reporting.technical import (  # noqa: E402
    memory_diff_rows,
    observation_url,
)
from agentic_redteam.storage.runs import RunStorage  # noqa: E402

RUNS_ROOT = REPO_ROOT / "runs"
CONFIG = REPO_ROOT / "config" / "target.yaml"
GENERATE_N = 2


def main() -> None:
    st.set_page_config(page_title="Agentic Red Team", page_icon="■", layout="wide")
    _inject_styles()
    st.title("Agentic Red Team")
    st.caption("Документы цели → профиль (LLM-судья) → проверка → OWASP-прогон. "
               "Сценарии — из OWASP, режимы — из профиля.")
    for key in ("profile_path", "docs", "last", "console"):
        st.session_state.setdefault(key, None if key != "console" else [])
    st.session_state.setdefault("report_preview", None)

    with st.sidebar:
        st.markdown("## Цель")
        base_url = st.text_input("Endpoint (base_url)", value="http://localhost:8600")
        st.markdown("### Документы (загружаются вручную)")
        openapi = st.file_uploader("OpenAPI · обязательно", type=["json", "yaml", "yml"])
        arch = st.file_uploader("Архитектура", type=["mmd", "md", "txt"])
        system_card = st.file_uploader("System card", type=["md", "txt"])
        extra = st.file_uploader("Доп. файлы: compose, схемы, исходники памяти",
                                 accept_multiple_files=True)
        left, right = st.columns(2)
        do_check = left.button("ПРОВЕРКА", width="stretch")
        do_run = right.button("ЗАПУСК", type="primary", width="stretch")
        _saved_run_picker()

    if do_check or do_run:
        if openapi is None:
            st.error("Загрузите OpenAPI цели.")
            return
        path = _build_profile(openapi, base_url, arch, system_card, extra)
        if path is None:
            return
        st.session_state.profile_path = str(path)

    profile_path = st.session_state.profile_path
    if profile_path:
        st.success(f"Профиль собран из документов: `{Path(profile_path).name}`")
        profile = load_profile(profile_path)
        with st.expander("Секции профиля"):
            st.json(_profile_summary(profile_path))
        if do_check:
            _do_check(profile)
        if do_run:
            _do_run(profile, st.session_state.docs or [])

    _render_results()


def _build_profile(openapi, base_url, arch, system_card, extra):
    tmp = Path(tempfile.mkdtemp())
    op = tmp / (openapi.name or "openapi.json")
    op.write_bytes(openapi.getvalue())
    docs: list[str] = []
    for upload in (arch, system_card, *(extra or [])):
        if upload is None:
            continue
        dest = tmp / upload.name
        dest.write_bytes(upload.getvalue())
        docs.append(str(dest))
    st.session_state.docs = docs
    try:
        roles = _role_configs_at(CONFIG)
        analyst = make_llm_client(roles["analyst"])
        judge = make_llm_client(roles["judge"])
    except Exception as exc:  # noqa: BLE001
        st.error(f"LLM для онбординга не настроен: {exc}")
        return None
    name = "target-" + op.stem
    with st.spinner("Собираю профиль из документов (analyst → judge)… пара минут"):
        try:
            draft = build_draft(str(op), base_url, name,
                                documents=docs, analyst=analyst, judge=judge)
            TargetProfile.from_mapping(draft)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Онбординг не удался: {exc}")
            return None
    out = tmp / "profile.yaml"
    out.write_text(yaml.safe_dump(draft, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    return out


def _profile_summary(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {
        "adapter": data.get("adapter"),
        "identities": (data.get("identities") or {}).get("provider"),
        "tools": [t.get("name") for t in (data.get("surface") or {}).get("tools", [])],
        "memory": [m.get("id") for m in (data.get("surface") or {}).get("memory", [])],
        "evidence": [(e.get("id"), e.get("provider")) for e in data.get("evidence", [])],
        "modes": list((data.get("modes") or {})),
        "judgement": (data.get("ingest") or {}).get("judgement", {}).get("rejected", []),
    }


def _saved_run_picker() -> None:
    st.markdown("## Сохранённые отчёты")
    runs = [row for row in RunStorage(RUNS_ROOT).list_runs()
            if row.get("status") != "invalid"]
    if not runs:
        st.caption("Прогонов пока нет.")
        return
    by_id = {row["run_id"]: row for row in runs}
    selected = st.selectbox(
        "Прогон",
        list(by_id),
        format_func=lambda run_id: f"{run_id} · {by_id[run_id].get('status')}",
    )
    if st.button("ОТКРЫТЬ ОТЧЁТЫ", key="open-saved-run", width="stretch"):
        run_dir = Path(by_id[selected]["run_dir"])
        try:
            findings = RunStorage(RUNS_ROOT).load_json(run_dir, "findings.json")
        except (OSError, ValueError) as exc:
            st.error(f"Не удалось прочитать findings.json: {exc}")
            return
        st.session_state.last = {"run_dir": str(run_dir), "findings": findings}
        st.session_state.report_preview = None


def _do_check(profile):
    st.subheader("Проверка цели · read-only")
    try:
        with EvidenceBundle.from_profile(profile) as bundle:
            adapter = HttpChatAdapter.from_profile(profile)
            try:
                results = [r.to_dict() for r in check(bundle, adapter)]
            finally:
                adapter.close()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Проверка не выполнена: {exc}")
        return
    st.dataframe([{
        "ИСТОЧНИК": r["name"],
        "OK": "✓" if r["ok"] else "✗",
        "БЛОКИРУЮЩИЙ": "да" if r.get("blocking") else "нет",
        "СООБЩЕНИЕ": r.get("message", ""),
    } for r in results], width="stretch", hide_index=True)


def _do_run(profile, docs):
    st.subheader("Console")
    console: list[str] = []
    box = st.empty()

    def log(line: str) -> None:
        console.append(line)
        box.code("\n".join(console[-300:]), language="log")

    modes = list(profile.modes) or ["vulnerable"]
    log(f"$ run --baseline --generate {GENERATE_N} "
        f"--mode {','.join(modes)} --profile {profile.name}@{profile.version}")
    try:
        planned, _coverage = build_baseline(profile)
        log(f"OWASP → применимо сценариев: {len(planned)}")
        for item in planned:
            log(f"  · {item.id} [{item.attack_class}]")
        documents = [read_document(path) for path in docs]
        planned, _generation = _generate_payloads(
            planned, profile, GENERATE_N, CONFIG, documents=documents)
        log("генератор: пейлоады синтезированы")
    except Exception as exc:  # noqa: BLE001
        log(f"! подготовка не удалась: {exc}")
        st.error(str(exc))
        return

    run_id = new_run_id()

    def on_event(event) -> None:
        verdict = event.data.get("verdict")
        log(f"[{event.stage}] {event.message}" + (f" → {verdict}" if verdict else ""))

    try:
        with st.spinner("Прогон OWASP-атаки на живой цели…"):
            summary = execute_campaign(
                profile, planned, modes, 1, RUNS_ROOT, run_id,
                reporter_llm=reporter_from_config(CONFIG), on_event=on_event,
                authorization=authorization_from_mapping(
                    _config_mapping(CONFIG)).as_record(),
                telemetry=telemetry_from_config(CONFIG),
                config=_config_mapping(CONFIG))
        run_dir = Path(summary["run_dir"])
        st.session_state.last = {
            "run_dir": str(run_dir),
            "findings": RunStorage(RUNS_ROOT).load_json(run_dir, "findings.json"),
        }
        st.session_state.report_preview = None
        log(f"готово · {summary['run_id']}")
    except Exception as exc:  # noqa: BLE001
        log(f"! прогон не удался: {exc}")
        st.error(str(exc))


def _render_results():
    last = st.session_state.last
    if not last:
        return
    findings = last["findings"]
    run_dir = Path(last["run_dir"])
    observability_path = run_dir / "observability.json"
    if not findings.get("observability") and observability_path.exists():
        findings["observability"] = RunStorage(run_dir.parent).load_json(
            run_dir, "observability.json"
        )
    st.subheader("Результат")
    scored = int(findings.get("scenarios_scored", 0) or 0)
    proven = int(findings.get("scenarios_proven", 0) or 0)
    a, b, c = st.columns(3)
    a.metric("ASR", f"{findings.get('asr_percent', 0)}%")
    b.metric("Сценарии proven", f"{proven}/{scored}")
    c.metric("Попыток", findings.get("attempts_total", 0))

    attempts_tab, evidence_tab, report_tab, files_tab = st.tabs(
        ("ПОПЫТКИ", "ДОКАЗАТЕЛЬСТВА", "ОТЧЁТ", "ФАЙЛЫ")
    )
    with attempts_tab:
        st.dataframe([{
            "СЦЕНАРИЙ": a.get("scenario_id"),
            "OWASP": a.get("attack_class"),
            "РОЛИ": a.get("roles"),
            "VERDICT": a.get("verdict"),
            "ПРИЗНАК": a.get("signal"),
        } for a in findings.get("attempts", [])],
            width="stretch", hide_index=True)
    with evidence_tab:
        _render_evidence(findings)

    reports = {
        "Технический": run_dir / "report.md",
        "Бизнес": run_dir / "business-report.md",
    }
    available = {name: path for name, path in reports.items() if path.exists()}
    with report_tab:
        if not available:
            st.info("Отчёт появится после прогона.")
        else:
            selected = st.segmented_control(
                "Вид отчёта", list(available), default=next(iter(available)),
                label_visibility="collapsed",
            ) or next(iter(available))
            preview_key = str(available[selected])
            label = (
                "СКРЫТЬ PREVIEW" if st.session_state.report_preview == preview_key
                else "ОТКРЫТЬ PREVIEW MARKDOWN"
            )
            if st.button(label, key="toggle-report-preview", type="primary"):
                st.session_state.report_preview = (
                    None if st.session_state.report_preview == preview_key else preview_key
                )
            if st.session_state.report_preview == preview_key:
                st.markdown("---")
                st.markdown(available[selected].read_text(encoding="utf-8"))
            else:
                st.caption("Preview скрыт. Откройте его кнопкой, когда понадобится полный документ.")
    with files_tab:
        if available:
            for name, report in available.items():
                st.download_button(
                    f"Скачать {name.lower()} отчёт",
                    report.read_bytes(), file_name=report.name,
                    mime="text/markdown", width="stretch",
                )
        else:
            st.info("Отчёт появится после прогона.")


def _render_evidence(findings: dict) -> None:
    rows = findings.get("findings") or []
    if not rows:
        st.info("Подтверждённых находок нет — показывать нечего.")
        return
    trace_url = (findings.get("observability") or {}).get("trace_url")
    for index, finding in enumerate(rows):
        severity = str(finding.get("severity") or "—").upper()
        title = f"{severity} · {finding.get('scenario_id') or finding.get('attack_class')}"
        with st.expander(title, expanded=index == 0):
            compromise = html.escape(str(
                finding.get("compromise_point") or "Точка компрометации не описана"
            ))
            st.markdown(
                f"<div class='finding-lead'><span>ПОДТВЕРЖДЕНО</span>"
                f"{compromise}</div>",
                unsafe_allow_html=True,
            )
            left, right = st.columns((3, 1))
            with left:
                st.caption("ДОКАЗАТЕЛЬНАЯ ЦЕПОЧКА")
                st.markdown(_ui_chain_graph(
                    finding.get("chain") or [], finding.get("problem_step")
                ), unsafe_allow_html=True)
                chain_rows = []
                for step in finding.get("chain") or []:
                    problem = step.get("name") == finding.get("problem_step")
                    event = _ui_step_event(step)
                    chain_rows.append({
                        "СТАТУС": "🔴 НАРУШЕНИЕ" if problem else "✓ ПРОЙДЕН",
                        "ШАГ": step.get("name"),
                        "РОЛЬ / PRINCIPAL": f"{step.get('role')} / {step.get('principal')}",
                        "СОБЫТИЕ": event,
                        "OBSERVATION": step.get("observation_id") or "—",
                    })
                st.dataframe(chain_rows, width="stretch", hide_index=True)
                problem = next((step for step in finding.get("chain") or []
                                if step.get("name") == finding.get("problem_step")), None)
                if problem:
                    st.caption("ЗАПРОС")
                    st.code(problem.get("request") or "—", language=None)
                    st.caption("ОТВЕТ АГЕНТА")
                    st.code(problem.get("response") or "—", language=None)
                memory_rows = memory_diff_rows(finding.get("chain") or [])
                st.caption("ПАМЯТЬ · ДО → ПОСЛЕ")
                if memory_rows:
                    st.dataframe([{
                        "ШАГ": row[0], "ХРАНИЛИЩЕ": row[1], "ИЗМЕНЕНИЕ": row[2],
                        "КЛЮЧ": row[3], "ДО": row[4], "ПОСЛЕ": row[5],
                    } for row in memory_rows], width="stretch", hide_index=True)
                else:
                    st.caption("Подтверждённых изменений памяти нет.")
            with right:
                st.caption("TRACE")
                observation_id = finding.get("observation_id")
                st.code(observation_id or "observation отсутствует", language=None)
                deep_link = observation_url(trace_url, observation_id)
                if deep_link:
                    st.link_button("Открыть проблемный span ↗", deep_link,
                                   width="stretch")
                elif trace_url:
                    st.link_button("Открыть полную трассу ↗", trace_url,
                                   width="stretch")
                st.caption("LOCAL EVIDENCE")
                for ref in finding.get("evidence_refs") or []:
                    st.code(ref, language=None)


def _ui_step_event(step: dict) -> str:
    calls = step.get("tool_calls") or []
    if calls:
        call = calls[0]
        return f"{call.get('tool')} → principal {call.get('principal')}"
    writes = step.get("memory_writes") or []
    if writes:
        write = writes[0]
        return f"memory {write.get('store')} · {write.get('scope')}"
    callbacks = step.get("callbacks") or []
    if callbacks:
        return f"callback {callbacks[0].get('source')}"
    return "ответ получен" if step.get("response") else "сигналов нет"


def _ui_chain_graph(chain: list[dict], problem_step: str | None) -> str:
    if not chain:
        return "<div class='attack-chain empty'>Цепочка не сохранена</div>"
    nodes = []
    for step in chain:
        name = html.escape(str(step.get("name") or "шаг"))
        css = "danger" if step.get("name") == problem_step else "done"
        label = "НАРУШЕНИЕ" if css == "danger" else "ПРОЙДЕН"
        nodes.append(
            f"<span class='chain-node {css}'><small>{label}</small>{name}</span>"
        )
    return "<div class='attack-chain'>" + "<b>→</b>".join(nodes) + "</div>"


def _inject_styles() -> None:
    """Alfa-inspired, restrained evidence-console styling."""
    st.markdown("""
    <style>
      .stApp { background: #f5f3f0; color: #191919; }
      h1, h2, h3 { letter-spacing: -0.025em; font-weight: 600; }
      h1::after { content: ""; display: block; width: 42px; height: 5px;
                  margin-top: 12px; background: #ef3124; }
      [data-testid="stMetric"] { background: #ebe7e2; border: 0; border-radius: 2px;
                                padding: 18px 20px; }
      [data-testid="stMetricValue"] { letter-spacing: -0.04em; }
      .finding-lead { background: #201f1e; color: #f8f5f1; padding: 18px 20px;
                      margin: 2px 0 20px; line-height: 1.5; }
      .finding-lead span { color: #ff5c52; display: block; font-size: 11px;
                           font-weight: 800; letter-spacing: .12em; margin-bottom: 7px; }
      .attack-chain { display: flex; align-items: center; gap: 10px; overflow-x: auto;
                      padding: 4px 0 18px; }
      .attack-chain > b { color: #aaa39c; font-weight: 400; }
      .chain-node { min-width: 112px; padding: 10px 12px; background: #e7e2dc;
                    border-radius: 2px; font-size: 13px; font-weight: 650; }
      .chain-node small { display: block; font-size: 9px; letter-spacing: .1em;
                          color: #655f59; margin-bottom: 3px; }
      .chain-node.danger { color: #fff8f5; background: #c6241a; }
      .chain-node.danger small { color: #ffd1cc; }
      .stButton > button[kind="primary"], .stLinkButton > a {
        border-radius: 2px; font-weight: 650; letter-spacing: .02em;
      }
      [data-baseweb="tab-list"] { gap: 24px; }
      [data-baseweb="tab"] { font-weight: 650; letter-spacing: .04em; }
      code { border-radius: 2px !important; }
    </style>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
