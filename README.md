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
- `agentic_redteam/scenarios/` — четыре фиксированных YAML-сценария;
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

Меняйте модели только в `config/target.yaml`. Роли независимы:

- `attack_generator` генерирует adaptive BAC payloads;
- `target_agent` описывает фактически запущенные `RESEARCH_MODEL` и
  `SUMMARIZATION_MODEL` стенда;
- `report_writer` пишет технический отчёт по уже собранным evidence.

Для текущего стенда обе внутренние модели должны совпадать с
`llm.target_agent.model`. Применить выбранную target-модель безопасно можно
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

Одна команда `run` обслуживает adaptive и фиксированные сценарии. Список
параметров и точные идентификаторы доступны через
`python -m agentic_redteam run --help`. Флаг `--json` поддерживается командами,
которые возвращают результат. Exit codes: `0` — успех, `2` — ошибка аргументов
или конфигурации, `3` — preflight target, `4` — LLM provider, `5` — pipeline.

UI не предлагает временные provider/model overrides: он показывает значения из
YAML read-only. В нём доступны выбор сценария, CUS, число прогонов, auth mode,
preflight, прогресс, outcome, evidence trace, отчёт, файлы и история из `runs/`.

В блоке «Контекст цели» можно загрузить или отредактировать прямо в интерфейсе
схему архитектуры стенда (`arch.mmd`) и описание компонентов (`system-card.md`);
этот контекст подаётся генератору Adaptive BAC. Без изменений используются файлы
из `docs/target/`, отредактированный контент применяется только к текущему запуску.

## Артефакты

Каждый запуск создаёт изолированный `runs/<run-id>/`:

- `config.json` — redacted effective config;
- `knowledge.jsonl` — evidence каждой попытки;
- `findings.json` — детерминированные verdict и ASR;
- `report.md` — LLM-отчёт, не участвующий в scoring;
- `status.json` — crash-tolerant состояние запуска;
- `observability.json` — trace ID/URL, observation IDs и warning экспорта.

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
