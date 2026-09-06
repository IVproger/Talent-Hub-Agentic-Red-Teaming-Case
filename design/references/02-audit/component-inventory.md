# Каталог компонентов

Интерфейс собран из двух слоёв: стандартные виджеты Streamlit, перекрашенные
через CSS, и восемь кастомных HTML-блоков со своими классами. Третьего слоя
(своих React-компонентов, `components.v1.html`, внешних библиотек) нет.

Пощупать блоки в браузере: [`../05-gallery/components.html`](../05-gallery/components.html).

## Кастомные HTML-блоки

Все восемь собираются конкатенацией строк и выводятся через
`st.markdown(..., unsafe_allow_html=True)`.

| Класс | Что это | Функция | Кадр |
| --- | --- | --- | --- |
| `.page-head` | Шапка: название + подзаголовок, линия снизу | `_page_header()` | [04](../01-screens/04-page-header.png) |
| `.scenario-meta` | Класс атаки и ATLAS под селектором сценария | `_scenario_card_html()` | [02](../01-screens/02-sidebar-default.png) |
| `.config-source` / `.model-row` | Три роли LLM из `config/target.yaml`, read-only | `_configured_models_html()` | [07](../01-screens/07-component-model-rows.png) |
| `.scenario-summary` / `.scenario-title` / `.step-line` | Карточка сценария: заголовок, id, описание, цепочка шагов, ATLAS | `_render_scenario_summary()` | [05](../01-screens/05-scenario-summary.png) |
| `.result-summary` / `.result-title` / `.ratio-track` | Итог прогона: вердикт, 4 метрики в grid, полоса доли | `_render_outcome_summary()` | [19](../01-screens/19-component-result-summary.png) |
| `.check-row` | Строка preflight: PASS/FAIL, имя, сообщение | `_render_preflight_checks()` | [12](../01-screens/12-component-check-rows.png) |
| `.live-log` / `.live-row` | Последние 6 событий прогона | `_live_progress_html()` | [30](../01-screens/30-component-live-log.png) |
| `.trace-rail` / `.trace-node` | Шаги попытки: имя, CUS, tool calls, дельта памяти | `_trace_rail_html()` | [22](../01-screens/22-component-trace-rail.png) |

Общая механика: минимальная разметка, разделители линиями `--line`,
подписи через `<small>` цветом `--muted`, никаких теней, скруглений,
иконок и цветовых акцентов. Единственный «крупный» элемент во всём
интерфейсе — `.result-summary` с вердиктом в 1.5rem.

## Виджеты Streamlit

Считано по исходнику: 26 разных вызовов API, 18 из них — `st.markdown`.

| Виджет | Раз | Где | Что с ним делает CSS |
| --- | --- | --- | --- |
| `st.markdown` | 18 | всюду | 8 вызовов несут кастомный HTML, остальные — заголовки и отчёт |
| `st.error` | 10 | валидация формы, ошибки прогона, повреждённая история | перекрашен в серый `--surface`, иконка обесцвечена |
| `st.expander` | 5 | модели, контекст цели, preflight, шаги трейса, история | `border-radius:0`, рамка `--line` |
| `st.selectbox` | 4 | сценарий, режим авторизации, выбор прогона, сохранённый запуск | **правило не применяется**, остаётся дефолтный вид |
| `st.dataframe` | 4 | попытки, проверки, история, tool calls | рамка `--line`, содержимое не стилизовано |
| `st.columns` | 4 | CUS, кнопки, запрос/ответ, файлы | — |
| `st.caption` | 4 | подсказки под формой и под итогом | — |
| `st.info` | 3 | пустые состояния | серый блок, неотличим от error |
| `st.code` | 3 | запрос, ответ, изменения памяти | рамка `--line`, `border-radius:0` |
| `st.text_input` | 2 | CUS атакующего, CUS цели | рамка `--line` |
| `st.text_area` | 2 | архитектура, описание компонентов | не стилизован |
| `st.file_uploader` | 2 | `.mmd`, system card | не стилизован, английские подписи |
| `st.form_submit_button` | 2 | ПРОВЕРИТЬ, ЗАПУСТИТЬ | secondary и disabled работают, **primary — нет** |
| `st.warning` | 2 | предупреждение observability | серый блок, неотличим от info |
| `st.tabs` | 1 | РЕЗУЛЬТАТ / ТРЕЙС / ОТЧЁТ / ФАЙЛЫ | подчёркивание активной работает, отступы — нет |
| `st.number_input` | 1 | число прогонов | рамка `--line` |
| `st.progress` | 1 | прогресс прогона | **правило не применяется**, красится темой |
| `st.download_button` | 1 | 5 артефактов прогона | квадратный, инверсия на hover |
| `st.link_button` | 1 | открыть трассу Langfuse | цвет ссылки принудительно `--ink` |
| `st.button` | 1 | ОТКРЫТЬ прогон из истории | квадратный, инверсия на hover |
| `st.json` | 1 | finalize facts | не стилизован |
| `st.spinner` | 1 | во время preflight | не стилизован |

`st.session_state` — 35 обращений, восемь ключей (`run_in_progress`,
`run_error`, `last_run_dir`, `last_result`, `environment_checks`,
`environment_fingerprint`, `arch_error`, `card_error`), инициализация
в `_init_state()`.

## Компоненты, которых нет, но которые подразумеваются продуктом

- диаграмма архитектуры цели (`arch.mmd` только загружается);
- карточка/бейдж severity — в отчётной части `agentic_redteam/reporting/`
  severity есть, в UI не выведена;
- сравнение двух прогонов;
- индикатор связи со стендом вне модального preflight;
- любые графики: `st.line_chart` / `st.bar_chart` / plotly в коде отсутствуют.
