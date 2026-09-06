"""Streamlit UI: документы цели → профиль (LLM-судья) → агентный ReAct-запуск.

Цель задаётся endpoint'ом и загруженными документами (без захардкоженного
реестра). «ЗАПУСК» собирает профиль (если ещё не собран) и запускает атаку в
фоновом потоке, поэтому разделы ПРОГОН и ИСТОРИЯ независимы и доступны, пока
запуск идёт. Движок — тот же `execute_agentic_campaign`, что и CLI.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentic_redteam.app_cli import (  # noqa: E402
    _agentic_budget,
    _config_mapping,
    _role_configs_at,
    execute_agentic_campaign,
    load_profile,
    make_llm_client,
    new_run_id,
)
from agentic_redteam.profile.ingest import build_draft, read_document  # noqa: E402
from agentic_redteam.profile.schema import TargetProfile  # noqa: E402
from agentic_redteam.storage.runs import RunStorage  # noqa: E402

RUNS_ROOT = REPO_ROOT / "runs"
CONFIG = REPO_ROOT / "config" / "target.yaml"

# Кооперативная отмена: событие на run_id, живёт в процессе (поток и скрипт —
# один процесс). Отмена срабатывает между шагами/сценариями фонового запуска.
_RUN_CANCEL: dict[str, threading.Event] = {}

# Последний собранный профиль (процесс-локально): сборка идёт в фоновом потоке,
# который сессию Streamlit трогать не может, поэтому путь публикуется сюда, а
# главный скрипт синхронизирует его в session_state.
_TARGET: dict = {"path": None, "docs": []}

# Верстка по design/ (Alfa Core Components, light-витрина): акцент — красный
# #ef3124 (задаёт тема; красная кнопка одна — «ЗАПУСК»), слои — цветом
# поверхности и радиусом, а не тенью; крупные скругления, pill-переключатели,
# системный sans, настоящий «знак» Альфы в хедере.
_ZNAK = (
    '<svg viewBox="0 0 370 370" width="30" height="30" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="370" height="370" fill="#ef3124"/>'
    '<rect x="114.28" y="258.75" width="141.44" height="29.39" fill="#fff"/>'
    '<path fill="#fff" d="M210.89,94.41c-4.03-12.03-8.68-21.53-24.61-21.53s-20.87,9.46-25.12,'
    '21.53l-43.77,124.41h29.02l10.1-29.58h55.84l9.37,29.58h30.86l-41.71-124.41Zm-45.91,69.85l'
    '19.84-58.96h.73l18.74,58.96h-39.31Z"/></svg>'
)

_BRAND_CSS = """
<style>
:root{
  --alfa-red:#ef3124; --alfa-red-hover:#e32a17; --alfa-red-press:#d72505;
  --bg:#ffffff; --bg-alt:#f2f3f5; --ink:#030306; --ink-2:rgba(4,4,19,.55);
  --line:#e6e7ea; --pos:#0cc44d; --neg:#ff4837;
}
.block-container{padding-top:2.2rem; max-width:1360px;}
h1,h2,h3{letter-spacing:-.02em; font-weight:800;}
/* чип статуса цели */
.art-chip{display:inline-flex; align-items:center; padding:6px 14px; border-radius:999px;
  background:var(--bg-alt); color:var(--ink-2); font-weight:600; font-size:.9rem; border:1px solid var(--line);}
.art-chip-ok{color:var(--ink);}
.art-chip-ok::first-letter{color:var(--pos);}
.art-chip-run{color:var(--ink); background:#fff5e6; border-color:#ffe0b3;}
.art-chip-run::first-letter{color:#fa9313;}
/* пустое состояние ЗАПУСКА — витринная карточка; «нажмите здесь» — часть текста */
.art-empty{display:flex; flex-direction:column; align-items:center; justify-content:center;
  text-align:center; gap:.6rem; padding:72px 24px; background:var(--bg-alt);
  border-radius:24px; color:var(--ink-2);}
.art-link{color:var(--alfa-red); font-weight:700; text-decoration:none;}
.art-link:hover{text-decoration:underline;}
.art-empty-mark{width:44px; height:44px; border-radius:12px; background:var(--bg);
  border:1px solid var(--line); display:flex; align-items:center; justify-content:center;
  color:var(--alfa-red); font-weight:800; font-size:1.3rem;}
.art-empty-title{font-weight:800; font-size:1.15rem; color:var(--ink); letter-spacing:-.01em;}
.art-empty-sub{font-size:.92rem; max-width:420px;}
/* кнопки: единственная красная — «ЗАПУСК» (тема), остальное вторичное */
.stButton>button{border-radius:999px; font-weight:600; border:1px solid var(--line);}
.stButton>button:not([kind="primary"]):not([kind="tertiary"]){background:var(--bg-alt); color:var(--ink);}
.stButton>button:not([kind="primary"]):not([kind="tertiary"]):hover{border-color:var(--ink-2);}
/* третичная кнопка = выделенный текст-действие (accent, без заливки/рамки) */
.stButton>button[kind="tertiary"]{background:transparent; border:none; color:var(--alfa-red); font-weight:700;}
.stButton>button[kind="tertiary"]:hover{background:transparent; color:var(--alfa-red-hover); text-decoration:underline;}
/* табы — сегментированный переключатель-капсула Альфы */
.stTabs [data-baseweb="tab-list"]{background:var(--bg-alt); border-radius:999px; padding:4px; gap:4px;}
.stTabs [data-baseweb="tab"]{border-radius:999px; padding:6px 20px; font-weight:600; color:var(--ink-2);}
.stTabs [aria-selected="true"]{background:var(--bg); color:var(--ink);}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"]{display:none;}
/* стат-карточки Альфы: слой поверхностью и радиусом, без тени */
[data-testid="stMetric"]{background:var(--bg-alt); border-radius:16px; padding:14px 18px;}
[data-testid="stMetricValue"]{font-weight:800;}
/* компактная вторичная кнопка (третичное действие — «скачать отчёт») */
[data-testid="stDownloadButton"] button{
  border-radius:999px; font-weight:600; padding:2px 14px; font-size:.82rem;
  background:var(--bg-alt); color:var(--ink); border:1px solid var(--line);
}
[data-testid="stDownloadButton"] button:hover{border-color:var(--ink-2);}
/* поля и таблицы — мягкое скругление, без теней */
[data-testid="stDataFrame"]{border-radius:16px; overflow:hidden; border:1px solid var(--line);}
.stTextInput input{border-radius:12px;}
/* русификация дропзоны файлов (дефолтные строки Streamlit — только через CSS) */
[data-testid="stFileUploaderDropzoneInstructions"] span{font-size:0;}
[data-testid="stFileUploaderDropzoneInstructions"] span::after{
  content:"Перетащите файлы сюда"; font-size:.92rem; color:var(--ink);}
[data-testid="stFileUploaderDropzoneInstructions"] small{font-size:0;}
[data-testid="stFileUploaderDropzoneInstructions"] small::after{
  content:"до 200 МБ на файл • JSON, YAML, YML, MMD, MD, TXT"; font-size:.78rem; color:var(--ink-2);}
[data-testid="stFileUploaderDropzone"] button *{display:none;}
[data-testid="stFileUploaderDropzone"] button::after{content:"Выбрать файлы"; font-size:.85rem;}
/* брендовый хедер со «знаком» */
.art-brand{display:flex; align-items:center; gap:.65rem; margin:0 0 .1rem;}
.art-znak{display:inline-flex; border-radius:8px; overflow:hidden; line-height:0;}
.art-name{font-weight:800; font-size:1.4rem; letter-spacing:-.02em; color:var(--ink);}
.art-rule{height:3px; width:56px; background:var(--alfa-red); border-radius:999px; margin:.4rem 0 1.1rem;}
</style>
"""

_BRAND_HEADER = (
    f'<div class="art-brand"><span class="art-znak">{_ZNAK}</span>'
    '<span class="art-name">Agentic Red Team</span></div>'
    '<div class="art-rule"></div>'
)


def main() -> None:
    st.set_page_config(page_title="Agentic Red Team", page_icon="■", layout="wide")
    st.markdown(_BRAND_CSS, unsafe_allow_html=True)
    st.markdown(_BRAND_HEADER, unsafe_allow_html=True)
    st.caption("MOROK автоматизирует полный цикл agentic red teaming — "
               "строго в авторизованном контуре.")
    for key in ("profile_path", "docs", "current_run", "history_open"):
        st.session_state.setdefault(key, None)
    # профиль, собранный фоновым потоком, подхватываем в сессию
    if _TARGET["path"] and not st.session_state.profile_path:
        st.session_state.profile_path = _TARGET["path"]
        st.session_state.docs = _TARGET.get("docs") or st.session_state.docs
    st.session_state.setdefault("section", "ЗАПУСК")
    # после «Запустить» окно закрывается и раздел переключается на «ЗАПУСК»
    if st.session_state.pop("goto_run", False):
        st.session_state.section = "ЗАПУСК"
    # inline-ссылка «нажмите здесь» из заглушки открывает окно через ?new=1
    if st.query_params.get("new"):
        st.query_params.clear()
        _new_attack_dialog()

    # Верхняя панель — статус текущего запуска (полезная информация) + компактный вход
    cls, text = _top_status()
    bar = st.columns([5, 1], vertical_alignment="center")
    with bar[0]:
        st.markdown(f'<span class="art-chip {cls}">{text}</span>', unsafe_allow_html=True)
    with bar[1]:
        if st.button("＋ Новая атака", use_container_width=True):
            _new_attack_dialog()

    section = st.segmented_control("Раздел", ["ЗАПУСК", "ИСТОРИЯ"],
                                   key="section", label_visibility="collapsed")
    if section == "ИСТОРИЯ":
        _render_history()
    else:
        _render_run()


@st.dialog("Новая атака", width="large")
def _new_attack_dialog():
    """Отдельное окно старта атаки: цель + документы + «ЗАПУСК».

    Профиль кэшируется: если он уже собран и новых документов не загрузили —
    «ЗАПУСК» сразу стартует запуск, не пересобирая.
    """
    built = bool(st.session_state.profile_path)
    base_url = st.text_input("Endpoint (base_url)", value="http://localhost:8600")
    files = st.file_uploader(
        "Документы цели — одним списком (OpenAPI, arch, system card, compose…)",
        type=["json", "yaml", "yml", "mmd", "md", "txt"], accept_multiple_files=True)
    st.caption("OpenAPI (JSON/YAML с разделом `paths`) находится автоматически; "
               "для новой цели он обязателен, остальные файлы — как документы.")
    if built and not files:
        st.success("Профиль уже собран — «Запустить» стартует сразу. "
                   "Загрузите файлы с новым OpenAPI, чтобы пересобрать цель.")
    if built and st.button("Сбросить цель", key="reset_target"):
        st.session_state.profile_path = None
        _TARGET["path"] = None
        st.rerun()
    if st.button("Запустить", type="primary", use_container_width=True):
        if bool(files) or not built:
            prep = _prepare_uploads(files)
            if prep is None:
                st.error("Среди файлов нет OpenAPI (JSON/YAML с разделом `paths`). Добавьте его.")
                return
            _start_run(build=(prep[0], prep[1], base_url))
        else:
            _start_run()  # переиспользуем собранный профиль
        st.rerun()  # окно закрывается сразу; сборка и статус — во вкладке «ЗАПУСК»


def _find_openapi(paths):
    """OpenAPI среди загруженных — первый JSON/YAML с dict-разделом `paths`."""
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("paths"), dict):
            return path
    return None


def _prepare_uploads(files):
    """Сохранить загруженные файлы (быстро, в главном потоке) и найти OpenAPI.

    Возвращает (op_path, doc_paths) или None, если OpenAPI не найден. LLM-сборка
    здесь НЕ делается — она идёт в фоновом потоке, чтобы окно закрылось сразу.
    """
    tmp = Path(tempfile.mkdtemp())
    saved = []
    for upload in files or []:
        dest = tmp / upload.name
        dest.write_bytes(upload.getvalue())
        saved.append(dest)
    op = _find_openapi(saved)
    if op is None:
        return None
    return str(op), [str(p) for p in saved if p != op]


def _build_profile_bg(op_path, doc_paths, base_url):
    """Онбординг профиля из документов (analyst → judge). Без Streamlit —
    вызывается из фонового потока. Возвращает путь к profile.yaml."""
    roles = _role_configs_at(CONFIG)
    analyst = make_llm_client(roles["analyst"])
    judge = make_llm_client(roles["judge"])
    name = "target-" + Path(op_path).stem
    draft = build_draft(op_path, base_url, name,
                        documents=doc_paths, analyst=analyst, judge=judge)
    TargetProfile.from_mapping(draft)
    out = Path(op_path).parent / "profile.yaml"
    out.write_text(yaml.safe_dump(draft, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    return str(out)


def _run_time(run_id):
    """Время запуска из его id (формат YYYYMMDD-HHMMSS-hash)."""
    try:
        return datetime.strptime(str(run_id)[:15], "%Y%m%d-%H%M%S")
    except (ValueError, TypeError):
        return None


def _top_status():
    """(css-класс чипа, текст) для верхней панели — статус текущего запуска."""
    run_id = st.session_state.get("current_run")
    if not run_id:
        return "", "◇ Запусков ещё не было — начните новую атаку"
    storage = RunStorage(RUNS_ROOT)
    try:
        status = storage.load_json(storage.root / run_id, "status.json")
    except (OSError, ValueError):
        return "art-chip-run", "🟡 Запуск инициализируется…"
    state = status.get("status")
    if state == "failed":
        return "", "🔴 Последний запуск не удался"
    if state == "interrupted":
        return "", "🟠 Последний запуск отменён"
    if state in ("running", "pending"):
        return "art-chip-run", f"🟡 Идёт запуск · {status.get('label') or 'инициализация…'}"
    try:
        f = storage.load_json(storage.root / run_id, "findings.json")
        return "art-chip-ok", (f"🟢 Завершён · ASR {f.get('asr_percent', 0)}% · "
                               f"proven {f.get('scenarios_proven', 0)}/{f.get('scenarios_scored', 0)}")
    except (OSError, ValueError):
        return "art-chip-ok", "🟢 Запуск завершён"


def _start_run(build=None) -> None:
    """Стартовать запуск в фоне. `build=(op_path, doc_paths, base_url)` — сначала
    собрать профиль в потоке; иначе переиспользовать уже собранный."""
    config = _config_mapping(CONFIG)
    budget = _agentic_budget(config, None)
    run_id = new_run_id()
    profile_path = st.session_state.profile_path
    docs = list(st.session_state.docs or [])
    storage = RunStorage(RUNS_ROOT)
    storage.write_json(storage.root / run_id, "status.json",
                       {"run_id": run_id, "status": "running",
                        "label": "Создание профиля" if build else "Подготовка"})
    cancel = threading.Event()
    _RUN_CANCEL[run_id] = cancel
    threading.Thread(target=_bg_run, daemon=True,
                     args=(run_id, profile_path, docs, build, config, budget, cancel)).start()
    st.session_state.current_run = run_id
    st.session_state.history_open = None
    st.session_state.goto_run = True  # после старта перейти в раздел «ЗАПУСК»


def _bg_run(run_id, profile_path, docs, build, config, budget, cancel) -> None:
    """Фоновый запуск: (опц.) сборка профиля → кампания. Streamlit не трогает."""
    storage = RunStorage(RUNS_ROOT)

    def progress(label: str) -> None:
        storage.write_json(storage.root / run_id, "status.json",
                           {"run_id": run_id, "status": "running", "label": label})

    extra_phases = None
    try:
        if build is not None:
            op_path, doc_paths, base_url = build
            progress("Создание профиля")
            started = time.perf_counter()
            profile_path = _build_profile_bg(op_path, doc_paths, base_url)
            extra_phases = [{"name": "Создание профиля",
                             "seconds": round(time.perf_counter() - started, 3)}]
            _TARGET["path"] = profile_path
            _TARGET["docs"] = doc_paths
            docs = doc_paths
        profile = load_profile(profile_path)
        documents = [read_document(path) for path in docs]
        execute_agentic_campaign(profile, config, RUNS_ROOT, run_id,
                                 budget=budget, documents=documents,
                                 extra_phases=extra_phases, should_stop=cancel.is_set,
                                 on_progress=progress)
    except Exception as exc:  # noqa: BLE001
        storage.write_json(storage.root / run_id, "status.json",
                           {"run_id": run_id, "status": "failed", "error": str(exc)})


@st.fragment(run_every=2)
def _poll_running(run_id: str) -> None:
    """Лёгкий авто-обновляемый статус. По завершении — один полный rerun,
    чтобы результат отрисовался статично (внутренние вкладки не сбрасывались)."""
    try:
        status = RunStorage(RUNS_ROOT).load_json(RUNS_ROOT / run_id, "status.json")
    except (OSError, ValueError):
        status = {"status": "running"}
    if status.get("status") in ("completed", "failed", "interrupted"):
        st.rerun()
    else:
        cancelling = _RUN_CANCEL.get(run_id) is not None and _RUN_CANCEL[run_id].is_set()
        detail = ("останавливаю после текущего шага…" if cancelling
                  else status.get("label") or "инициализация…")
        st.markdown(f'<span class="art-chip art-chip-run">◐ {detail}</span>',
                    unsafe_allow_html=True)


def _render_run() -> None:
    run_id = st.session_state.get("current_run")
    if not run_id:
        st.markdown(
            '<div class="art-empty"><div class="art-empty-mark">▟</div>'
            '<div class="art-empty-title">Здесь появится ваш запуск</div>'
            '<div class="art-empty-sub">Статус, попытки, тайминги и отчёт будут показаны '
            'здесь. Чтобы создать новый запуск — '
            '<a href="?new=1" target="_self" class="art-link">нажмите здесь</a>.</div></div>',
            unsafe_allow_html=True)
        return
    storage = RunStorage(RUNS_ROOT)
    run_dir = storage.root / run_id
    try:
        status = storage.load_json(run_dir, "status.json")
    except (OSError, ValueError):
        status = {"status": "running"}
    state = status.get("status")
    if state == "failed":
        st.error(f"Запуск `{run_id}` не удался: {status.get('error', '')}")
        if st.session_state.profile_path and st.button("Повторить запуск", key="retry_run"):
            _start_run()
            st.rerun()
        return
    if state not in ("completed", "interrupted"):
        st.caption(f"Запуск `{run_id}`")
        left, right = st.columns([4, 1], vertical_alignment="center")
        with left:
            _poll_running(run_id)
        with right:
            if st.button("Отменить", key="cancel_run", use_container_width=True):
                event = _RUN_CANCEL.get(run_id)
                if event is not None:
                    event.set()
                st.toast("Отмена запрошена — запуск остановится после текущего шага.")
                st.rerun()
        return
    try:
        findings = storage.load_json(run_dir, "findings.json")
    except (OSError, ValueError):
        findings = None
    if state == "interrupted":
        st.warning("Запуск отменён — ниже частичный результат (успевшие сценарии).")
        if st.session_state.profile_path and st.button("Повторить запуск", key="retry_run"):
            _start_run()
            st.rerun()
    if findings is None:
        st.info("Запуск завершается…")
        return
    _render_results(run_dir, findings)


def _render_results(run_dir: Path, findings: dict, key: str = "run") -> None:
    st.subheader("Результат")
    scored = int(findings.get("scenarios_scored", 0) or 0)
    proven = int(findings.get("scenarios_proven", 0) or 0)
    a, b, c = st.columns(3)
    a.metric("ASR", f"{findings.get('asr_percent', 0)}%")
    b.metric("Сценарии proven", f"{proven}/{scored}")
    c.metric("Попыток", findings.get("attempts_total", 0))

    attempts_tab, timings_tab, report_tab = st.tabs(("ПОПЫТКИ", "ТАЙМИНГИ", "ОТЧЁТ"))
    with attempts_tab:
        st.dataframe([{
            "СЦЕНАРИЙ": a.get("scenario_id"),
            "OWASP": a.get("attack_class"),
            "VERDICT": a.get("verdict"),
            "ЦЕЛЬ": a.get("target") or "—",
            "ШАГОВ": len(a.get("steps", [])),
            "СЕК": a.get("seconds", "—"),
        } for a in findings.get("attempts", [])],
            use_container_width=True, hide_index=True)
    with timings_tab:
        _render_timings(findings.get("timings") or {})
    report = run_dir / "report.md"
    with report_tab:
        if report.exists():
            st.download_button("Скачать отчёт (.md)", report.read_bytes(),
                               file_name=f"{run_dir.name}-report.md", mime="text/markdown",
                               key=f"dl-{key}-{run_dir.name}")
            st.markdown(report.read_text(encoding="utf-8"))
        else:
            st.info("Отчёт появится после запуска.")


def _render_timings(timings: dict) -> None:
    phases = timings.get("phases") or []
    if not phases:
        st.info("Тайминги недоступны для этого запуска.")
        return
    st.metric("Итого, сек", timings.get("total_seconds", 0))
    st.caption("По фазам")
    st.dataframe([{"ФАЗА": p["name"], "СЕК": p["seconds"]} for p in phases],
                 use_container_width=True, hide_index=True)
    st.bar_chart(pd.DataFrame({"сек": [p["seconds"] for p in phases]},
                              index=[p["name"] for p in phases]))
    per = timings.get("per_scenario") or []
    if per:
        st.caption("По сценариям (фаза «Атака»)")
        st.dataframe([{"СЦЕНАРИЙ": x.get("scenario_id"), "СЕК": x.get("seconds")} for x in per],
                     use_container_width=True, hide_index=True)


def _render_history() -> None:
    """Список ИЛИ деталь (не одновременно): открытый запуск занимает всю ширину,
    список — компактный и скроллится, чтобы не растягивать страницу."""
    try:
        history = RunStorage(RUNS_ROOT).list_runs()
    except Exception:  # noqa: BLE001
        history = []
    if not history:
        st.info("Запусков пока нет.")
        return

    open_id = st.session_state.get("history_open")
    if open_id:
        storage = RunStorage(RUNS_ROOT)
        run_dir = storage.root / open_id
        try:
            findings = storage.load_json(run_dir, "findings.json")
        except (OSError, ValueError, TypeError, KeyError):
            findings = None
        if st.button("← К списку запусков"):
            st.session_state.history_open = None
            st.rerun()
        when = _run_time(open_id)
        ts = f" · {when.strftime('%d.%m.%Y %H:%M')}" if when else ""
        st.caption(f"Запуск `{open_id}`{ts}")
        if findings is None:
            st.error("Результаты запуска повреждены или не завершены.")
        else:
            _render_results(run_dir, findings, key="hist")
        return

    dot = {"completed": "🟢", "failed": "🔴", "interrupted": "🟠",
           "running": "🟡", "pending": "🟡", "invalid": "⚪"}
    status_ru = {"completed": "завершён", "failed": "не удался", "interrupted": "отменён",
                 "running": "идёт", "pending": "в очереди", "invalid": "нет данных"}
    status_opts = {"все": None, "завершён": "completed", "не удался": "failed",
                   "отменён": "interrupted", "нет данных": "invalid"}

    query = st.text_input("Поиск по id/дате", key="hist_query",
                          placeholder="напр. 20260906 или f27306").strip().lower()
    choice = st.segmented_control("Статус", list(status_opts), key="hist_status",
                                  default="все", label_visibility="collapsed")
    want = status_opts.get(choice)

    # сортировка ранние → поздние (run_id начинается с YYYYMMDD-HHMMSS)
    ordered = sorted(history, key=lambda it: str(it.get("run_id") or ""))
    rows = [it for it in ordered
            if (want is None or it.get("status") == want)
            and (not query or query in str(it.get("run_id") or "").lower())]

    st.caption(f"Запуски · {len(rows)}/{len(history)} — выберите, чтобы открыть")
    with st.container(height=430):
        if not rows:
            st.caption("Ничего не найдено.")
        for item in rows:
            rid = item.get("run_id")
            status = str(item.get("status", "unknown"))
            asr = item.get("asr_percent")
            openable = status not in ("invalid", "running") and isinstance(rid, str)
            asr_txt = f" · ASR {asr}%" if isinstance(asr, (int, float)) else ""
            when = _run_time(rid)
            ts = when.strftime("%d.%m.%Y %H:%M") if when else str(rid)
            short = str(rid).split("-")[-1]
            if st.button(f"{dot.get(status, '⚪')}  {ts} · {short}{asr_txt}", key=f"hist_{rid}",
                         use_container_width=True, disabled=not openable,
                         help=f"{rid} · {status_ru.get(status, status)}"):
                st.session_state.history_open = rid
                st.rerun()


if __name__ == "__main__":
    main()
