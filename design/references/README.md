# output/ — отправная точка для редизайна UI

Полный снимок того, как выглядит и из чего состоит текущий интерфейс MOROK
(Streamlit-приложение `agentic_redteam/ui/app.py`) на 5 сентября 2026 года.
Собрано с живого запущенного приложения: скриншоты реальные, не макеты.

Материал нужен, чтобы редизайн начинался не с чистого листа и не с догадок,
а с точного понимания: какие экраны есть, какие состояния они принимают,
какими компонентами собраны, какие правила оформления действуют и что из них
уже сломано.

## С чего начать

| Если вам нужно | Откройте |
| --- | --- |
| Увидеть продукт целиком за минуту | [01-screens/01-default-desktop.png](01-screens/01-default-desktop.png), затем [17c](01-screens/17c-result-compromised-tall.png) и [21](01-screens/21-result-tab-trace-tall.png) |
| Понять, что чинить в первую очередь | [02-audit/redesign-baseline.md](02-audit/redesign-baseline.md) |
| Разобрать интерфейс на экраны и блоки | [02-audit/page-inventory.md](02-audit/page-inventory.md) |
| Найти конкретный компонент и его класс | [02-audit/component-inventory.md](02-audit/component-inventory.md) |
| Перебрать все состояния при проектировании | [02-audit/state-matrix.md](02-audit/state-matrix.md) |
| Забрать тексты и термины | [02-audit/copy-inventory.md](02-audit/copy-inventory.md) |
| Взять цвета, шрифты, размеры в работу | [03-tokens/design-tokens.json](03-tokens/design-tokens.json) |
| Пощупать компоненты в браузере | [05-gallery/components.html](05-gallery/components.html) |
| Прочитать текущий CSS одним куском | [04-source/styles.css](04-source/styles.css) |

## Состав

```text
output/
├── README.md                     этот файл
│
├── 01-screens/                   40 PNG @2x с живого приложения
│   └── README.md                 подпись к каждому кадру
│
├── 02-audit/                     разбор текущего интерфейса
│   ├── page-inventory.md         структура страницы, зоны, порядок блоков
│   ├── component-inventory.md    все виджеты и кастомные блоки, где применяются
│   ├── state-matrix.md           состояния каждой зоны и чем они вызваны
│   ├── copy-inventory.md         тексты интерфейса целиком
│   └── redesign-baseline.md      находки, дефекты и разрыв с целевой концепцией
│
├── 03-tokens/                    оформление в машинном виде
│   ├── current-theme.toml        копия .streamlit/config.toml
│   ├── design-tokens.json        тема + CSS-переменные + шкала размеров
│   ├── computed-styles.json      реально применённые стили, снятые с DOM
│   └── selector-health.json      какие CSS-селекторы приложения ещё работают
│
├── 04-source/
│   ├── app.py                    снимок исходника UI на момент съёмки
│   └── styles.css                CSS из `_styles()`, извлечён и отформатирован
│
├── 05-gallery/
│   ├── components.html           каталог кастомных блоков, открывается в браузере
│   └── components-preview.png    его же скриншот
│
└── _tooling/                     чем всё это собрано, воспроизводимо
    ├── make_fixtures.py          синтетические прогоны в runs/ для съёмки
    ├── capture_ui.py             прогон по интерфейсу и съёмка
    ├── live_state_harness.py     рендер состояний, живущих только во время запуска
    ├── extract_styles.py         вытяжка CSS и токенов из app.py
    └── build_gallery.py          сборка каталога компонентов
```

## Что важно знать про этот снимок

**Интерфейс — одна страница.** Не пять экранов, а один скролл: сайдбар с формой
слева, результат последнего прогона справа. Всё, что в целевой концепции
([`artifacts/product-artifacts/07-concept-ui-description.md`](../artifacts/product-artifacts/07-concept-ui-description.md))
разложено по шагам пользовательского пути, сейчас лежит в одном месте.
Подробнее — в [redesign-baseline.md](02-audit/redesign-baseline.md).

**Оформление живёт в одном месте.** Весь дизайн — это один вызов
`st.markdown(..., unsafe_allow_html=True)` внутри функции `_styles()`
в [`agentic_redteam/ui/app.py:781`](../agentic_redteam/ui/app.py#L781): 77 строк
CSS, пять переменных цвета, один шрифт. Плюс шесть строк темы
в [`.streamlit/config.toml`](../.streamlit/config.toml). Больше нигде стилей нет.

**Часть CSS уже не работает.** Шесть селекторов написаны под структуру DOM
старых версий Streamlit и в текущей (1.63) не совпадают ни с одним узлом —
из-за этого главная кнопка «ЗАПУСТИТЬ» не выделена, а поля ввода остались
скруглёнными вопреки замыслу. Проверено на живом DOM, список в
[selector-health.json](03-tokens/selector-health.json) и разбор в
[redesign-baseline.md](02-audit/redesign-baseline.md).

**Скриншоты сняты на синтетических прогонах.** Реальный прогон требует
поднятого стенда, Docker и ключей провайдера. Чтобы снять вкладки результата,
трейс, отчёт и историю, в `runs/` положены два детерминированных прогона
из `_tooling/make_fixtures.py` — данные вымышленные, формат настоящий.
Preflight на скриншотах, наоборот, настоящий: две проверки честно падают,
потому что стенд не поднят.

## Как пересобрать

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install playwright && python -m playwright install chromium

python3 output/_tooling/make_fixtures.py
python3 -m streamlit run agentic_redteam/ui/app.py --server.port 8599 &
python3 output/_tooling/capture_ui.py 8599

python3 -m streamlit run output/_tooling/live_state_harness.py --server.port 8601 &
# кадры 29-34 снимаются с этого адреса

python3 output/_tooling/extract_styles.py
python3 output/_tooling/build_gallery.py
python3 output/_tooling/make_fixtures.py --clean
```

Съёмка велась на Streamlit 1.63.0, Chromium 148, viewport 1512×950 @2x.
