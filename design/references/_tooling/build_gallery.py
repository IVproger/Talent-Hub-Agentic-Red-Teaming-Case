#!/usr/bin/env python3
"""Живой каталог кастомных HTML-компонентов текущего UI.

Собирает страницу из настоящего CSS приложения и настоящей разметки: там,
где в app.py есть чистая функция (`_scenario_card_html`, `_live_progress_html`,
`_trace_rail_html`, `_configured_models_html`), вызывается она; два блока,
собранные инлайном в `_render_outcome_summary` и `_page_header`, повторены
по исходнику один в один.

Открывается в браузере, ничего не запускает. Нужен, чтобы редизайн видел
разметку и классы, а не только картинки.

    python3 output/_tooling/build_gallery.py
    open output/05-gallery/components.html
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentic_redteam.llm import LLMRoleConfig  # noqa: E402
from agentic_redteam.ui.app import (  # noqa: E402
    _configured_models_html,
    _live_progress_html,
    _scenario_card_html,
    _trace_rail_html,
)

OUT = REPO_ROOT / "output" / "05-gallery"
CSS = REPO_ROOT / "output" / "04-source" / "styles.css"
OUT.mkdir(parents=True, exist_ok=True)


def _role(model: str) -> LLMRoleConfig:
    return LLMRoleConfig(
        provider="openrouter",
        model=model,
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        temperature=0,
        timeout=600,
    )


PAGE_HEAD = """
<header class="page-head">
  <h1>Agentic Red Team</h1>
  <p>Сценарии безопасности агента с проверкой по состоянию.</p>
</header>
"""

SCENARIO_SUMMARY = (
    '<section class="scenario-summary"><div class="scenario-title">'
    "<h2>Adaptive BAC / Tool Argument</h2>"
    "<code>generated-bac</code></div>"
    "<p>LLM генерирует вариативные запросы; успех фиксируется только по "
    "cross-CUS аргументу реального tool call.</p>"
    '<div class="step-line"><span>generate</span><i>→</i><span>probe</span>'
    "<i>→</i><span>observe</span><i>→</i><span>verdict</span></div>"
    "<small>tool_argument_bac · AML.T0012 · AML.T0077</small></section>"
)

RESULT_SUMMARY = (
    '<section class="result-summary">'
    '<div class="result-title"><span>ИТОГ</span>'
    "<strong>COMPROMISED</strong><small>20260905-104500-uiref-bac</small></div>"
    "<dl>"
    "<div><dt>ASR</dt><dd>40%</dd></div>"
    "<div><dt>Подтверждено</dt><dd>2/5</dd></div>"
    "<div><dt>Evidence</dt><dd>5 / 10</dd></div>"
    "<div><dt>Статус</dt><dd>COMPLETED</dd></div>"
    "</dl>"
    '<div class="ratio-track"><i style="width:40.00%"></i></div></section>'
)

CHECK_ROWS = (
    '<div class="check-row"><b>PASS</b><span><strong>stand</strong>'
    "<small>Каталог с исходниками стенда доступен.</small></span></div>"
    '<div class="check-row"><b>FAIL</b><span><strong>llm_config</strong>'
    "<small>report_writer: OpenRouter is selected but OPENROUTER_API_KEY is not set."
    " Export the key before starting the run.</small></span></div>"
    '<div class="check-row"><b>PASS</b><span><strong>docker</strong>'
    "<small>Исполняемый файл Docker доступен.</small></span></div>"
)

EVENTS = [
    {"stage": "preflight", "message": "Стенд и провайдеры проверены.", "verdict": None},
    {"stage": "generate", "message": "Сгенерировано 5 кандидатов payload.", "verdict": None},
    {"stage": "attempt", "message": "Попытка 2/5 · cross-CUS аргумент в tool call.", "verdict": "proven"},
    {"stage": "report", "message": "Собираем технический отчёт…", "verdict": None},
]

STEPS = [
    {"name": "generate", "actor_cus": "1001", "tool_calls": [], "new_global_policies": []},
    {"name": "probe", "actor_cus": "1001", "tool_calls": [{}], "new_global_policies": []},
    {"name": "observe", "actor_cus": "1002", "tool_calls": [], "new_global_policies": [{}]},
    {"name": "verdict", "actor_cus": "1001", "tool_calls": [], "new_global_policies": []},
]

BLOCKS = [
    (
        "page-head",
        "Шапка страницы",
        "`_page_header()` — единственный заголовок продукта. Название слева, "
        "подзаголовок справа, разделительная линия цвета --ink.",
        PAGE_HEAD,
    ),
    (
        "scenario-meta",
        "Мета сценария (сайдбар)",
        "`_scenario_card_html()` — класс атаки слева, ATLAS-техники справа, 0.64rem.",
        _scenario_card_html({"attack_class": "tool_argument_bac", "atlas": ["AML.T0012", "AML.T0077"]}),
    ),
    (
        "config-source / model-row",
        "Модели из конфигурации (сайдбар)",
        "`_configured_models_html()` — read-only список ролей LLM из config/target.yaml.",
        _configured_models_html(
            {
                "attack_generator": _role("z-ai/glm-5.3-flash"),
                "target_agent": _role("qwen/qwen3-8b"),
                "report_writer": _role("z-ai/glm-5.3-flash"),
            }
        ),
    ),
    (
        "scenario-summary / step-line",
        "Карточка выбранного сценария",
        "`_render_scenario_summary()` — заголовок, id, описание, цепочка шагов, класс и ATLAS.",
        SCENARIO_SUMMARY,
    ),
    (
        "result-summary / ratio-track",
        "Итог прогона",
        "`_render_outcome_summary()` — единственный «крупный» элемент интерфейса: "
        "вердикт, 4 метрики в grid и полоса доли подтверждённых попыток.",
        RESULT_SUMMARY,
    ),
    (
        "check-row",
        "Строки preflight",
        "`_render_preflight_checks()` — PASS/FAIL, имя проверки, сообщение.",
        CHECK_ROWS,
    ),
    (
        "live-log / live-row",
        "Живой лог прогона",
        "`_live_progress_html()` — последние 6 событий, показывается только во время запуска.",
        _live_progress_html(EVENTS),
    ),
    (
        "trace-rail / trace-node",
        "Рейка шагов трейса",
        "`_trace_rail_html()` — шаги попытки с числом tool call и дельтой памяти.",
        _trace_rail_html(STEPS),
    ),
]

DOC = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agentic Red Team · каталог текущих UI-компонентов</title>
<style>
{app_css}
</style>
<style>
/* Обвязка каталога — не часть продукта. */
body {{ background:var(--paper); color:var(--ink); margin:0; padding:3rem clamp(1rem,5vw,5rem) 6rem; }}
.gallery-head {{ border-bottom:1px solid var(--ink); padding-bottom:1rem; margin-bottom:2.5rem; }}
.gallery-head h1 {{ font-size:1.35rem; margin:0 0 .5rem; }}
.gallery-head p {{ color:var(--muted); font-size:.75rem; max-width:70ch; margin:0; line-height:1.6; }}
.block {{ border-top:1px solid var(--line); padding:2rem 0 2.5rem; }}
.block-head {{ display:flex; align-items:baseline; gap:1rem; justify-content:space-between; margin-bottom:.5rem; }}
.block-head h2 {{ font-size:.95rem !important; margin:0; }}
.block-head code {{ font-size:.62rem; color:var(--muted) !important; }}
.block>p {{ color:var(--muted); font-size:.7rem; max-width:78ch; margin:0 0 1.25rem; line-height:1.6; }}
.demo {{ background:var(--paper); border:1px dashed var(--line); padding:1.5rem; margin-bottom:1rem; }}
.demo--surface {{ background:var(--surface); }}
details.markup {{ border:1px solid var(--line); }}
details.markup summary {{ cursor:pointer; padding:.5rem .75rem; font-size:.64rem; letter-spacing:.04em; }}
details.markup pre {{ margin:0; padding:.75rem; border-top:1px solid var(--line); overflow-x:auto;
  font-size:.62rem; line-height:1.6; background:var(--surface); }}
</style>
</head>
<body>
<header class="gallery-head">
  <h1>Каталог текущих UI-компонентов</h1>
  <p>Все кастомные HTML-блоки Streamlit-приложения, собранные настоящим CSS
  продукта и настоящими функциями из <code>agentic_redteam/ui/app.py</code>.
  Страница статическая: она показывает исходное состояние перед редизайном,
  включая блоки, которые в живом интерфейсе видны только во время прогона.</p>
</header>
{blocks}
</body>
</html>
"""

BLOCK_TEMPLATE = """<section class="block">
  <div class="block-head"><h2>{title}</h2><code>{selector}</code></div>
  <p>{note}</p>
  <div class="demo{surface}">{markup}</div>
  <details class="markup"><summary>РАЗМЕТКА</summary><pre>{escaped}</pre></details>
</section>
"""


def main() -> None:
    from html import escape

    blocks = []
    for selector, title, note, markup in BLOCKS:
        surface = " demo--surface" if "сайдбар" in title.lower() else ""
        blocks.append(
            BLOCK_TEMPLATE.format(
                title=title,
                selector=escape(selector),
                note=note,
                markup=markup,
                escaped=escape(markup.strip()),
                surface=surface,
            )
        )
    app_css = CSS.read_text(encoding="utf-8") if CSS.is_file() else ""
    # В каталоге нет Streamlit — правила под его data-testid только мешают.
    streamlit_only = (
        "[data-testid",
        "[data-baseweb",
        "[aria-selected",
        ".stApp",
        ".stButton",
        ".stDownloadButton",
        ".stFormSubmitButton",
        ".stAlertContainer",
        ".block-container",
    )
    app_css = "\n".join(
        line for line in app_css.splitlines() if not line.startswith(streamlit_only)
    )
    target = OUT / "components.html"
    target.write_text(DOC.format(app_css=app_css, blocks="\n".join(blocks)), encoding="utf-8")
    print(f"написано: {target}")


if __name__ == "__main__":
    main()
