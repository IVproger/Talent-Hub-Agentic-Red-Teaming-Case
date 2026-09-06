"""Рендер тех состояний UI, которые живут только во время прогона.

Прогресс-бар, живой лог `_live_progress_html`, активная кнопка ЗАПУСТИТЬ и
spinner существуют лишь пока идёт `run_pipeline`, и в обычной съёмке их не
поймать. Harness импортирует настоящие функции `agentic_redteam.ui.app`
и рисует их с фиксированными данными — стили те же, что в продукте.

    python3 -m streamlit run output/_tooling/live_state_harness.py --server.port 8600
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentic_redteam.ui.app import (  # noqa: E402
    _live_progress_html,
    _page_header,
    _render_preflight_checks,
    _scenario_card_html,
    _styles,
    _trace_rail_html,
)

st.set_page_config(page_title="Agentic Red Team · live states", page_icon="■", layout="wide")
_styles()
_page_header()

EVENTS = [
    {"stage": "preflight", "message": "Стенд и провайдеры проверены.", "verdict": None},
    {"stage": "generate", "message": "Сгенерировано 5 кандидатов payload.", "verdict": None},
    {"stage": "attempt", "message": "Попытка 1/5 · probe отправлен.", "verdict": "not_proven"},
    {"stage": "attempt", "message": "Попытка 2/5 · cross-CUS аргумент в tool call.", "verdict": "proven"},
    {"stage": "attempt", "message": "Попытка 3/5 · probe отправлен.", "verdict": "not_proven"},
    {"stage": "report", "message": "Собираем технический отчёт…", "verdict": None},
]

st.markdown("### Прогресс запуска")
st.progress(0.62, text="Попытка 3/5 · observe")
st.markdown(_live_progress_html(EVENTS), unsafe_allow_html=True)

st.markdown("### Кнопки формы")
left, right = st.columns(2)
with left:
    st.button("ПРОВЕРИТЬ", width="stretch")
with right:
    st.button("ЗАПУСТИТЬ", type="primary", width="stretch")
st.button("ЗАПУСТИТЬ (disabled)", disabled=True, width="stretch")

st.markdown("### Preflight · всё зелёное")
_render_preflight_checks(
    [
        {"name": "stand", "ok": True, "message": "Каталог с исходниками стенда доступен."},
        {"name": "llm_config", "ok": True, "message": "Ключи всех ролей заданы."},
        {"name": "docker", "ok": True, "message": "Исполняемый файл Docker доступен."},
        {"name": "docker_compose", "ok": True, "message": "Docker Compose доступен."},
        {"name": "agent_api", "ok": True, "message": "Целевой agent API отвечает на /healthz."},
    ]
)

st.markdown("### Trace rail")
st.markdown(
    _trace_rail_html(
        [
            {"name": "generate", "actor_cus": "1001", "tool_calls": [], "new_global_policies": []},
            {"name": "probe", "actor_cus": "1001", "tool_calls": [{}], "new_global_policies": []},
            {"name": "observe", "actor_cus": "1002", "tool_calls": [], "new_global_policies": [{}]},
            {"name": "verdict", "actor_cus": "1001", "tool_calls": [], "new_global_policies": []},
        ]
    ),
    unsafe_allow_html=True,
)

st.markdown("### Карточка сценария в сайдбаре")
st.markdown(
    _scenario_card_html({"attack_class": "tool_argument_bac", "atlas": ["AML.T0012", "AML.T0077"]}),
    unsafe_allow_html=True,
)

st.markdown("### Системные сообщения")
st.info("Проверьте конфигурацию и запустите сценарий.")
st.success("Готово · 20260905-104500-uiref-bac")
st.warning("Langfuse недоступен, трасса не выгружена.")
st.error("Конфигурация изменилась. Выполните preflight ещё раз.")
st.link_button("ОТКРЫТЬ ТРАССУ", "http://localhost:3001/")
