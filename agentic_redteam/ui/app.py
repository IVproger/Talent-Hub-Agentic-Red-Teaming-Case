"""Streamlit UI: документы цели → профиль (LLM-судья) → проверка → OWASP-прогон.

Цель задаётся endpoint'ом и загруженными документами (без захардкоженного
реестра). Сценарии берутся из OWASP, режимы — из профиля; пользователь только
проверяет цель и запускает атаку. Движок — тот же `execute_campaign`, что и CLI.
"""
from __future__ import annotations

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
from agentic_redteam.storage.runs import RunStorage  # noqa: E402

RUNS_ROOT = REPO_ROOT / "runs"
CONFIG = REPO_ROOT / "config" / "target.yaml"
GENERATE_N = 2


def main() -> None:
    st.set_page_config(page_title="Agentic Red Team", page_icon="■", layout="wide")
    st.title("Agentic Red Team")
    st.caption("Документы цели → профиль (LLM-судья) → проверка → OWASP-прогон. "
               "Сценарии — из OWASP, режимы — из профиля.")
    for key in ("profile_path", "docs", "last", "console"):
        st.session_state.setdefault(key, None if key != "console" else [])

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
        do_check = left.button("ПРОВЕРКА", use_container_width=True)
        do_run = right.button("ЗАПУСК", type="primary", use_container_width=True)

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
    } for r in results], use_container_width=True, hide_index=True)


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
    st.subheader("Результат")
    scored = int(findings.get("scenarios_scored", 0) or 0)
    proven = int(findings.get("scenarios_proven", 0) or 0)
    a, b, c = st.columns(3)
    a.metric("ASR", f"{findings.get('asr_percent', 0)}%")
    b.metric("Сценарии proven", f"{proven}/{scored}")
    c.metric("Попыток", findings.get("attempts_total", 0))

    attempts_tab, report_tab, files_tab = st.tabs(("ПОПЫТКИ", "ОТЧЁТ", "ФАЙЛЫ"))
    with attempts_tab:
        st.dataframe([{
            "СЦЕНАРИЙ": a.get("scenario_id"),
            "OWASP": a.get("attack_class"),
            "РОЛИ": a.get("roles"),
            "VERDICT": a.get("verdict"),
            "ПРИЗНАК": a.get("signal"),
        } for a in findings.get("attempts", [])],
            use_container_width=True, hide_index=True)
    report = run_dir / "report.md"
    with report_tab:
        st.markdown(report.read_text(encoding="utf-8") if report.exists() else "—")
    with files_tab:
        if report.exists():
            st.download_button("Скачать технический отчёт", report.read_bytes(),
                               file_name="report.md", mime="text/markdown",
                               use_container_width=True)
        else:
            st.info("Отчёт появится после прогона.")


if __name__ == "__main__":
    main()
