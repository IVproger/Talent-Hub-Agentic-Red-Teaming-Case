# 01-screens — что на каком кадре

40 снимков живого приложения. Retina @2x, шрифты загружены, ничего не
дорисовано. Кадры с суффиксом `-tall` сняты в высоком viewport (1512×2200),
чтобы длинная страница влезла целиком; `-desktop` — как это видит человек
на ноутбуке (1512×950).

Кадры 29–34 сняты с `_tooling/live_state_harness.py`: там собраны блоки,
которые в живом приложении существуют только пока идёт прогон.

## Экраны целиком

| Файл | Что показывает |
| --- | --- |
| `01-default-desktop.png` | Первое, что видит пользователь. Сайдбар с формой, шапка, карточка сценария, пустое состояние, свёрнутая история. |
| `09-scenario-scripted-desktop.png` | Тот же экран после выбора фиксированного сценария вместо Adaptive BAC. Меняется только карточка сценария. |
| `13-preflight-failed-desktop.png` | После нажатия «ПРОВЕРИТЬ»: раскрытый блок проверок с двумя FAIL, «ЗАПУСТИТЬ» заблокирован. |
| `17-result-incomplete-tall.png` | Загружен прерванный прогон: вердикт INCOMPLETE, ASR N/A, две ошибки подряд. |
| `17c-result-compromised-tall.png` | Загружен успешный прогон: вердикт COMPROMISED, ASR 40%, ссылка на трассу. |
| `18-result-tab-outcome-desktop.png` | Вкладка РЕЗУЛЬТАТ в реальном окне ноутбука. Виден разрыв: заголовок сценария сверху не тот, что в результате снизу. |
| `21-result-tab-trace-tall.png` | Вкладка ТРЕЙС целиком: таблица попыток, выбор прогона, рейка шагов, четыре шага-аккордеона, таблица проверок. |
| `25-result-tab-report-tall.png` | Вкладка ОТЧЁТ: `report.md` рендерится дефолтным markdown Streamlit, без оформления продукта. |
| `26-result-tab-files-desktop.png` | Вкладка ФАЙЛЫ: пять кнопок скачивания в две колонки. |
| `28-narrow-1024.png` | Окно 1024 px. Сайдбар держит фиксированные 360 px, таблицы теряют колонки справа. |
| `29-runtime-only-states.png` | Состояния времени прогона: прогресс-бар, живой лог, кнопки, зелёный preflight, все четыре типа системных сообщений. |
| `35-sidebar-collapsed.png` | Сайдбар свёрнут: основная область растягивается, кнопка разворота прибита в левый верхний угол. |

## Сайдбар

| Файл | Что показывает |
| --- | --- |
| `02-sidebar-default.png` | Исходное состояние формы: выбор сценария, два CUS, число прогонов, режим авторизации, два свёрнутых блока, ошибка про ключи, две кнопки. |
| `06-sidebar-models-expanded.png` | Раскрыт блок «Модели из конфигурации» — read-only список трёх ролей LLM. |
| `08-sidebar-target-context.png` | Раскрыт блок «Контекст цели»: два загрузчика файлов и два больших textarea. Самая тяжёлая часть формы. |
| `11-preflight-failed-sidebar.png` | Сайдбар после проверки: блок «Проверка · 3/5» с PASS/FAIL. |
| `14-form-validation-error.png` | Ошибка валидации «CUS должны состоять из цифр и различаться» рядом с ошибкой про ключи — два одинаковых серых блока подряд. |

## Компоненты крупным планом

| Файл | Компонент | Класс / источник |
| --- | --- | --- |
| `04-page-header.png` | Шапка продукта | `.page-head` |
| `05-scenario-summary.png` | Карточка выбранного сценария | `.scenario-summary`, `.step-line` |
| `10-scenario-scripted-summary.png` | Она же для фиксированного сценария | там же |
| `07-component-model-rows.png` | Список моделей из YAML | `.config-source`, `.model-row` |
| `12-component-check-rows.png` | Строки preflight | `.check-row` |
| `33-component-preflight-pass.png` | Они же, когда всё зелёное | `.check-row` |
| `16-component-history-table.png` | Таблица истории запусков | `st.dataframe` |
| `19-component-result-summary.png` | Итог прогона, COMPROMISED | `.result-summary`, `.ratio-track` |
| `17b-component-result-summary-incomplete.png` | Он же, INCOMPLETE | там же |
| `20-component-tabs.png` | Полоса вкладок | `st.tabs` |
| `20b-component-form-controls.png` | Форма запуска целиком | `st.form` |
| `22-component-trace-rail.png` | Рейка шагов | `.trace-rail`, `.trace-node` |
| `23-component-attempts-table.png` | Таблица попыток | `st.dataframe` |
| `24-component-step-expander.png` | Шаг трейса: запрос и ответ в двух колонках | `st.expander` + `st.code` |
| `24b-component-assertions-table.png` | Таблица проверок | `st.dataframe` |
| `24c-component-run-picker.png` | Выбор прогона | `st.selectbox` |
| `27-component-download-buttons.png` | Кнопки артефактов | `st.download_button` |
| `30-component-live-log.png` | Живой лог прогона | `.live-log`, `.live-row` |
| `31-component-progress-bar.png` | Прогресс-бар | `st.progress` |
| `32-component-buttons.png` | Кнопки рядом | `st.button` |
| `34-component-alerts.png` | info / success / warning / error подряд — визуально неразличимы | `st.info`, `st.success`, `st.warning`, `st.error` |
