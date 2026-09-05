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
- `agentic_redteam/scenarios/` — четыре фиксированных YAML-сценария,
  `scenarios/v2/` — они же в новом словаре предикатов;
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

- `attack_generator` генерирует adaptive BAC payloads;
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

```bash
# Поднять стенд.
docker compose -f stand/docker-compose.yml up -d --build

# Read-only preflight.
python -m agentic_redteam doctor

# Adaptive BAC: предварительный просмотр и реальный запуск.
python -m agentic_redteam run --scenario generated-bac --dry-run
python -m agentic_redteam run --scenario generated-bac --trials 5

# Один или несколько фиксированных сценариев через тот же pipeline.
python -m agentic_redteam run --scenario bac-tool-argument --trials 3
python -m agentic_redteam run \
  --scenario mem-policy-conformant \
  --scenario poison-to-tool-chain \
  --trials 2

# Пересобрать отчёт существующего нового запуска.
python -m agentic_redteam report --run runs/<run-id>

# Локальный desktop UI.
python -m agentic_redteam serve
```

Одна команда `run` обслуживает adaptive и фиксированные сценарии. Флаги
`--arch` и `--system-card` переопределяют контекст цели (схему архитектуры и
описание компонентов), который читает генератор Adaptive BAC; без них берутся
файлы из `docs/target/`. Список параметров и точные идентификаторы доступны
через `python -m agentic_redteam run --help`. Флаг `--json` поддерживается командами,
которые возвращают результат. Exit codes: `0` — успех, `2` — ошибка аргументов
или конфигурации, `3` — preflight target, `4` — LLM provider, `5` — pipeline.

UI не предлагает временные provider/model overrides: он показывает значения из
YAML read-only. В нём доступны выбор сценария, CUS, число прогонов, auth mode,
preflight, прогресс, outcome, evidence trace, отчёт, файлы и история из `runs/`.

В блоке «Контекст цели» можно загрузить или отредактировать прямо в интерфейсе
схему архитектуры стенда (`arch.mmd`) и описание компонентов (`system-card.md`);
этот контекст подаётся генератору Adaptive BAC. Без изменений используются файлы
из `docs/target/`, отредактированный контент применяется только к текущему запуску.

## Профиль и кампания (новый путь)

Всё знание о цели живёт в **профиле** — ядро о цели не знает. Профиль
описывает точку входа, роли, границы изоляции, инструменты, память, режимы и
источники evidence; секретов в нём нет, только имена переменных окружения.

```bash
# Что вообще есть в реестре.
python -m agentic_redteam profile list

# Карта поверхности: инструменты, память, границы, источники.
python -m agentic_redteam profile show --profile genai-invest-stand@1.0.0

# Что изменилось между версиями профиля.
python -m agentic_redteam profile diff genai-invest-stand@1.0.0 path/to/other.yaml

# Гейт покрытия: какие сценарии на этой цели вообще доказуемы состоянием.
python -m agentic_redteam profile coverage --profile genai-invest-stand@1.0.0

# Read-only проверка подключения и привязок источников evidence.
python -m agentic_redteam profile check --profile genai-invest-stand@1.0.0

# Проба видимости памяти. МЕНЯЕТ состояние цели: чистит память и пишет маркеры.
python -m agentic_redteam profile verify --profile genai-invest-stand@1.0.0
```

`coverage` сверяет источники, которые объявляет профиль, с теми, что требуют
предикаты сценария. Сценарий без своего источника честно помечается «нет
источника» — вердикт по нему не поднимется выше `indirect`, и знать это лучше
до прогона, а не после.

Кампания собирается флагами и предварительно показывается целиком:

```bash
# План и payload'ы до отправки — цель не затрагивается.
python -m agentic_redteam run --profile genai-invest-stand@1.0.0 \
  --scenario all --mode vulnerable,protected --dry-run

# Прогон: адаптер и evidence собираются из профиля.
python -m agentic_redteam run --profile genai-invest-stand@1.0.0 \
  --scenario poison-to-tool-chain --mode vulnerable,protected --trials 3

# Повтор сохранённой кампании из артефакта прогона.
python -m agentic_redteam run --from runs/<run-id> --dry-run
```

Перед прогоном срабатывает гейт покрытия: сценарий, для которого профиль не
объявляет нужного источника, **не запускается вовсе** и попадает в список
пропущенных. Прогнать его было бы хуже, чем пропустить — `not_proven` от
нехватки evidence неотличим от «атака не сработала».

Сценарии нового словаря лежат в `agentic_redteam/scenarios/v2/`. Сценарий —
это цепочка шагов (кто говорит и в каком порядке) плюс варианты payload'а,
которые подставляются в шаг с `payload: true`. Многошаговая атака —
внедрение → фиксация памяти → активация другой ролью — исполняется как **одна
попытка**: один сброс цели, одно окно evidence.

> `run --from` пока только предпросмотр (`--dry-run`). Старый путь запуска из
> раздела «Запуск» выше остаётся рабочим и уйдёт, когда новый заменит его целиком.

## Артефакты

Каждый запуск создаёт изолированный `runs/<run-id>/`:

- `config.json` — redacted effective config;
- `knowledge.jsonl` — evidence каждой попытки;
- `findings.json` — детерминированные verdict и ASR;
- `report.md` — LLM-отчёт, не участвующий в scoring;
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

Ошибочные попытки не входят в знаменатель ASR. При падении запуска сохраняются
частичные evidence и детерминированный incomplete report.

## Langfuse (опционально)

Инструкция запуска находится в [`deploy/langfuse/README.md`](deploy/langfuse/README.md).
Runner создаёт корневую `redteam.run` trace, а target продолжает её через
стандартный W3C `traceparent`. В одной трассе видны генерация атаки, попытки,
запросы к target, target LLM/ReAct, tool calls, memory/finalize, scoring и отчёт.

Tracing включён в YAML, но работает fail-open: Langfuse не вычисляет security
verdict и не заменяет локальные evidence. Без credentials или при недоступном
сервисе запуск продолжается, а проблема фиксируется только как warning. До
экспорта применяются redaction и ограничение размера значений.

## Проверка разработки

```bash
python -m unittest discover -s tests -v
python -m compileall -q agentic_redteam stand/app
git diff --check
```
