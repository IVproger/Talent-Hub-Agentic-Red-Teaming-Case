# Agentic Red Teaming

Инструмент для state-based проверки учебного инвестиционного агента. Успех
атаки определяется не текстом ответа модели, а наблюдаемым состоянием стенда:
реальным tool call с чужим `cus`, изменением памяти или другой детерминированной
проверкой сценария.

> Только для авторизованного тестирования. Каталог `stand/` — намеренно
> уязвимый локальный стенд с синтетическими данными.

## Структура

- `config/target.yaml` — единственный источник provider/model/base URL для трёх
  LLM-ролей и настроек запуска;
- `agentic_redteam/scenarios/` — четыре встроенных YAML-сценария;
- `profiles/<name>/<version>.yaml` — реестр профилей целей;
- `docs/target/` — архитектура и system card целевого стенда;
- `runs/<run-id>/` — артефакты новых запусков;
- `deploy/langfuse/` — опциональный локальный Langfuse v4;
- `stand/` — целевой агент, обычная отслеживаемая директория репозитория.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp stand/.env.example stand/.env
```

Укажите ключ целевого провайдера в `stand/.env` как `OPENAI_API_KEY`. Если
`attack_generator` или `report_writer` используют OpenRouter, экспортируйте
переменную, указанную в их `api_key_env` (по умолчанию `OPENROUTER_API_KEY`).
Секреты в YAML не хранятся.

## YAML — источник истины

Модели движка задаются в `config/target.yaml`, в секции `llm`. Роли независимы:

- `attack_generator` — генератор фиксированного набора payload-вариантов для
  `run --generate N`;
- `report_writer` пишет технический отчёт по уже собранным evidence.
- `analyst` предназначен для анализа и заполнения профиля цели.

Модель цели задаётся отдельно: `entrypoint.target_model` в
`profiles/genai-invest-stand/1.0.0.yaml`. Ссылка на этот файл — `target.profile`
в `config/target.yaml`. Для стенда `RESEARCH_MODEL` и `SUMMARIZATION_MODEL`
должны совпадать с этой декларацией; ключ остаётся внутри стенда.
Применить выбранную модель можно
явной командой:

```bash
# Показать изменения без записи и Docker-операций.
python -m agentic_redteam stand sync --dry-run

# Обновить только три model-поля в stand/.env, пересоздать agent-api и проверить его.
python -m agentic_redteam stand sync
```

Команда управляет только `OPENAI_BASE_URL`, `RESEARCH_MODEL` и
`SUMMARIZATION_MODEL`; `OPENAI_API_KEY`, token limits, комментарии и остальные
настройки сохраняются. `doctor` ничего не меняет и при drift предлагает `stand
sync`.

`stand sync` — инструмент настройки нашего `genai-invest-stand`, вне
target-независимого ядра MOROK. Он вызывается явно: обычный запуск кампании
не переписывает `.env` и не пересоздаёт сервисы. Другие цели настраиваются
своими средствами развёртывания; их профили используются адаптером и
evidence-провайдерами.

Bootstrap-профиль стенда составлен вручную и не требует OpenAPI-файла.
Для последующей демонстрации `profile init` можно отдельно сохранить схему
работающего стенда командой
`curl --fail http://localhost:8600/openapi.json -o docs/target/openapi.json`.
OpenAPI описывает HTTP-поверхность; привязки инструментов, памяти и evidence
в bootstrap-профиле проверяются отдельно через `evidence.calibrate`.

## Запуск

Всё знание о цели живёт в **профиле** — ядро о цели не знает. Профиль описывает
точку входа, роли, границы изоляции, инструменты, память, режимы и источники
evidence; секретов в нём нет, только имена переменных окружения.

```bash
# Поднять стенд.
docker compose -f stand/docker-compose.yml up -d --build

# Что есть в реестре и что цель вообще позволяет проверить.
python -m agentic_redteam profile list
python -m agentic_redteam profile show --profile genai-invest-stand@1.0.0
python -m agentic_redteam profile surface --profile genai-invest-stand@1.0.0 --check
python -m agentic_redteam profile coverage --profile genai-invest-stand@1.0.0

# Read-only проверка подключения и привязок источников.
python -m agentic_redteam profile check --profile genai-invest-stand@1.0.0
python -m agentic_redteam doctor --profile genai-invest-stand@1.0.0

# Проба видимости памяти. МЕНЯЕТ состояние цели: чистит память и пишет маркеры.
python -m agentic_redteam profile verify --profile genai-invest-stand@1.0.0

# Предпросмотр: план и payload'ы, цель не затрагивается.
python -m agentic_redteam run --profile genai-invest-stand@1.0.0 \
  --scenario all --mode vulnerable,protected --dry-run

# Прогон: адаптер и evidence собираются из профиля.
python -m agentic_redteam run --profile genai-invest-stand@1.0.0 \
  --scenario poison-to-tool-chain --mode vulnerable,protected --trials 3

# Повтор сохранённой кампании и пересборка отчёта.
python -m agentic_redteam run --from runs/<run-id> --dry-run   # предпросмотр
python -m agentic_redteam run --from runs/<run-id>             # исполнить повтор
python -m agentic_redteam report --run runs/<run-id>
python -m agentic_redteam report --business --run runs/<run-id>

# Регрессия: находки → набор, набор → прогон, прогон vs прогон.
python -m agentic_redteam regress export --from runs/<run-id> -o regress/bac
python -m agentic_redteam run --from regress/bac
python -m agentic_redteam regress compare --before runs/<a> --after runs/<b>

# Судьба находки: статус и его история.
python -m agentic_redteam kb list --profile genai-invest-stand
python -m agentic_redteam kb status <finding-id> --set fixed --note "закрыли привязку"

# Локальный desktop UI.
python -m agentic_redteam serve
```

**Авторизация обязательна.** Без блока `authorization` (`authorized_by`,
`scope`, `until`) в `config/target.yaml` прогон не стартует, а просроченное
окно — то же самое, что его отсутствие. Разрешение попадает в `campaign.json`.
Предпросмотр цель не трогает и разрешения не требует.

**Режим без записи** — `run --read-only`, для внешних целей: сценарий, который
по своим объявленным шагам пишет в цель (шаг с payload, `commit_memory`,
`reset_policy` кроме `none`), не запускается вовсе; остаётся только
наблюдение. Решение принимается из плана, до того как поднимутся провайдеры и
адаптер. Оговорка честная: режим запрещает то, что **объявлено** планом, — цель
может записать что-то себе сама в ответ на обычное сообщение, и из плана это не
видно. Флаг фиксируется в `campaign.json`.

`regress export` берёт из прогонов **только подтверждённые находки** и едущие
с ними штатные сценарии, складывая их в обычную сохранённую кампанию — поэтому
набор исполняется тем же `run --from`, а не отдельным путём. Повтор всегда
пишет новый `runs/<id>/`: исходные артефакты неизменны.

`regress compare` отвечает на два вопроса сразу: закрылась ли находка
(`перестала проходить` / `осталась` / `появилась`) и не сломался ли при этом
сам агент (штатный сценарий). Та же операция сравнивает режимы A/B.

`profile coverage` — гейт покрытия: сверяет источники, которые объявляет
профиль, с теми, что требуют предикаты сценария. Сценарий без своего источника
помечается «нет источника» и **не запускается вовсе**. Прогнать его было бы
хуже, чем пропустить: `not_proven` от нехватки evidence неотличим от «атака не
сработала».

`profile surface` строит единый per-agent threat model: точки входа, каналы
доставки, sensitive-инструменты, память, внешние интеграции, evidence и связи
между ними. Без `--check` заявленные компоненты остаются явно неподтверждёнными;
с `--check` команда выполняет только read-only калибровку и добавляет статус с
причиной. Тот же словарь сохраняется как `surface.json` запуска и отображается
в Streamlit — отдельной UI-логики карты нет. Сводка покрытия показывает только
доказуемые существующими state-предикатами пункты и не обещает полное покрытие
стандарта.

Сценарии лежат в `agentic_redteam/scenarios/`. Сценарий — это цепочка шагов
(кто говорит и в каком порядке) плюс варианты payload'а, которые подставляются
в шаг с `payload: true`. Многошаговая атака — внедрение → фиксация памяти →
активация другой ролью — исполняется как **одна попытка**: один сброс цели,
одно окно evidence.

Флаг `--json` поддерживается командами, которые возвращают результат.
Exit codes: `0` — успех, `2` — ошибка аргументов или конфигурации,
`3` — preflight target, `4` — LLM provider, `5` — прогон.

Ctrl+C останавливает прогон безопасно: собранное сохраняется со статусом
`interrupted`, технические ошибки в знаменатель ASR не входят.

Генерация payload'ов — `run --generate N`: генератор один раз пишет N вариантов
на сценарий (LLM только текст), список фиксируется до прогона и в цикле не
пересоздаётся. Дубли отсеиваются, контекст прошлых кампаний берётся из базы
знаний.

Рядом с ASR отчёт всегда показывает **покрытие и разнообразие**: пункты
стандарта, классы атак, число различных подходов и затронутую поверхность
(инструменты, хранилища, границы). ASR легко накрутить повтором одной удачной
попытки — покрытие нет.

## Артефакты

Каждый запуск создаёт изолированный `runs/<run-id>/`:

- `config.json` — redacted effective config;
- `findings.json` — детерминированные verdict и ASR;
- `report.md` — технический отчёт: доказавшая попытка и payload, пошаговая
  цепочка, state-сигналы, evidence-ссылки и воспроизведение; LLM-нарратив не
  участвует в scoring;
- `business-report.md` — отдельный E9-отчёт `риск / польза / следующий шаг`,
  создаётся командой `report --business` только из `proven`-находок;
- `status.json` — crash-tolerant состояние запуска;
- `observability.json` — trace ID/URL, observation IDs и warning экспорта;
- `campaign.json` — состав кампании (профиль, режимы, trials, сценарии с
  шагами и payload'ами); из него и повторяется прогон;
- `transcript.jsonl` — по строке на попытку: payload, режим, вердикт,
  градации предикатов, ошибка и ссылки на evidence;
- `evidence-NNNN.json` — для нового пути `run --profile`: факты и исходные
  наблюдения конкретной попытки. Ссылка на доказавшую попытку записывается
  в `findings.json` и `report.md`; техническая ошибка не получает чужие evidence.
  В `steps` сохранены роль, principal, сессия, ответ, facts и observations каждого
  шага. Предикат с `at` проверяет только этот шаг относительно его principal;
  `cross_session_effect` выбирает `activate`. Без `at` записи памяти собираются
  по цепочке, а проверки доступа сравнивают каждый шаг с его собственным актором.

После появления `observability.json` команда `report --run` добавляет в
технический отчёт trace ID, URL и root observation. Метрика «попыток до первого
proven» считает только атакующие попытки и не принимает успешный smoke за
найденную уязвимость.

Ошибочные попытки не входят в знаменатель ASR. При падении запуска сохраняются
частичные evidence и детерминированный incomplete report.

Бизнес-эффекты задаёт команда агента в `profile.business`. Для точного
сопоставления запрет может объявить `scenario_ids`, `attack_classes`,
`boundaries` или `standard_refs`, а `effect_ids` связывает его с полезными
эффектами. Если явной привязки нет, отчёт помечает вывод как предположительный;
финансовый ущерб без входных данных не рассчитывается.

## Langfuse (опционально)

Инструкция запуска находится в [`deploy/langfuse/README.md`](deploy/langfuse/README.md).
Runner создаёт корневую trace и наблюдение на каждую попытку; ссылка на трассу
сохраняется в `observability.json` прогона.

Tracing включён в YAML, но работает fail-open: Langfuse не вычисляет security
verdict и не заменяет локальные evidence. Без credentials или при недоступном
сервисе прогон продолжается, а проблема фиксируется только как warning. До
экспорта применяются redaction и ограничение размера значений.

Две разные вещи, которые легко спутать: **телеметрия нашего прогона** fail-open
и на вердикт не влияет; **Langfuse/OTLP как источник evidence** (провайдер
`trace` в профиле) — load-bearing, его отказ даёт `error`, а не пустой успех.

Адаптер пробрасывает W3C `traceparent` из корневой трассы кампании. Это даёт
сквозную связь с ReAct-циклом и tool calls цели, если целевая система продолжает
входящий контекст. Тестовый стенд это поддерживает; реальный экспорт всё равно
нужно проверять с настроенными Langfuse credentials.

## Проверка разработки

```bash
python -m unittest discover -s tests -v
python -m compileall -q agentic_redteam stand/app
git diff --check
```
