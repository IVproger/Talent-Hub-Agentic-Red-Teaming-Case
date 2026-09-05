# Evidence: настройка границы цели

Источники возвращают `Observation`; `EvidenceBundle` отвечает за преобразование
в `Facts`. Ошибка чтения обязательного источника должна доходить до runner как
ошибка попытки. Это отдельный путь от fail-open телеметрии нашего запуска.

## Bundle (задача 3.6)

`EvidenceBundle.from_profile(profile)` создаёт провайдеры секции `evidence`
и источники `surface.memory[].read` (под id `memory:<store-id>`). В тестах доступны
`runner=`, `readers={provider_id: reader}`, `provider_factories={name: factory}`.
Обычный конструктор принимает `{id: provider}` или список провайдеров и опциональный
`profile=` для `record`/`principal_from` привязок.

Перед запуском CLI должен вызвать `supports(scenario.goal)`; отсутствие источника
инструментальных действий исключает state-проверки. Цель, состоящая из tool-предикатов,
не требует memory snapshot. Неизвестный предикат не проходит гейт.

`mark()` фиксирует курсоры и снимки памяти **до** действия; `collect_facts(marker)`
собирает события и возвращает `Facts`. Новые записи и изменения содержимого/owner/scope
существующих ключей считаются memory writes; неизменённые записи не считаются.
`mark_all` / `collect_all` — алиасы с тем же непрозрачным одноразовым `Marker`.
Сырьё последней успешной сборки доступно через `last_observations` для сохранения
артефактов runner. Окно нельзя повторно использовать после сбора или reset.

`reset()` вызывает только источники `SESSION_RESET`. Отсутствие такого источника
даёт `UnsupportedFeature`: для цели без reset следует явно выбрать `reset_policy=none`.
Bootstrap стенда объявляет четыре коллекции памяти (без API keys) и Redis `working:*`.
Сброс не использует `FLUSHALL`; калибровка reset-провайдера только проверяет ping.
`close()` закрывает все ресурсы (включая canary); bundle поддерживает `with`.

## Check / verify (задача 3.7)

`check(bundle, adapter)` возвращает `list[doctor.CheckResult]`, не вызывает reset,
отправку сообщений или mint. Недоступность памяти помечается `blocking=False`,
поскольку это усилитель; гейт конкретной цели всё равно обязателен.

`verify(bundle, adapter)` меняет состояние и требует `SESSION_RESET`.
Перед пробой и в `finally` очищает память, отправляет уникальный безвредный маркер
ролью A, финализирует память при `MEMORY_COMMIT`, подтверждает запись снимком,
открывает отдельную сессию роли B и читает фактические виды памяти A/B.
Успех требует положительного контроля A. Для `cross_user/cross_session` ожидается
видимость B, для `per_user/session` — отсутствие. В session-проверках B означает
другую сессию того же принципала. Ответы LLM не используются как evidence.

Независимое чтение задаётся в `surface.memory[].read.config.visibility`:
`compose_file`, `service`, `module`, `factory`, необязательный `member`, `method`,
`arguments` (шаблоны `{principal}` / `{session}`). Провайдер вызывает объявленный
метод реального memory repository цели и читает его JSON-результат. Bootstrap
стенда использует `MongoMemoryStore.agent_policy.list_all()` и
`MongoMemoryStore.semantic.list_for_context(principal)`, то есть фактическую
фильтрацию цели. `probe_message` задаёт формат безвредного маркера под тип памяти.
При отсутствии независимого reader проба не выполняется и не объявляется успешной.

`entrypoint.verify` может задать `mode`, `writer_role`, `reader_role`,
`write_message` с `{marker}`, `read_message`. Ошибки записи, чтения, неоднозначный
scope и неудачная очистка дают отрицательный `CheckResult`.

## Trace (задача 3.5)

`TraceProvider(config, reader=None)` принимает `backend: langfuse | otel`,
`trace_id`, `tool_prefix` (по умолчанию `tool.`), `args_path` и `context_path`
(по умолчанию `attributes`), `principal_from` как в профиле инструмента.
При динамической корреляции вызывающий код вызывает `bind_trace(trace_id)` перед
`mark()`. Trace-id должен принадлежать запросу цели. Маркер фиксирует уже известные
span-id; при сборе они исключаются. Нельзя подставлять trace-id телеметрии MOROK,
если цель не продолжает тот же контекст.

Для Langfuse: `host`, `public_key_env`, `secret_key_env`, `api_version: 2`
(по умолчанию; `1` для старых инстансов). Читатель получает все страницы
Observations API и переводит JSON `input` в `attributes`; исходная запись остаётся
в `raw`. Можно задать `from_start_time`, `to_start_time`; иначе окно — последние
24 часа (`lookback_seconds`). Повтор курсора/превышение `max_pages` — ошибка,
а не частичный успешный результат.

Для OTLP: `path` к JSON/JSONL экспорту коллектора или `read_url` явно настроенного
read endpoint. Обычный `/v1/traces` — путь приёма, он не используется для чтения.
Поддерживаются `resourceSpans.scopeSpans.spans`, hex trace-id, typed attributes.
Неполная JSON-строка в ещё записываемом экспорте даёт ошибку чтения; вызывающий код
должен повторить чтение после завершения экспорта.

Калибровка read-only: проверяет уже существующие контрольные tool-спаны;
`calibration.expected_principal` позволяет проверить конкретный principal.
Асинхронная доставка спанов зависит от ingestion/exporter: вызывающий код должен
собирать evidence после подтверждённой доставки. Этот читатель не объявляет
пустой trace доказательством отсутствия действий.

Проверены форматы по официальным источникам:

- [Langfuse Observations API](https://langfuse.com/docs/api-and-data-platform/features/observations-api).
- [OTLP JSON encoding](https://opentelemetry.io/docs/specs/otlp/).
- [OTLP JSONL file exporter](https://opentelemetry.io/docs/specs/otel/protocol/file-exporter/).
- [MongoDB Shell: environment variables](https://www.mongodb.com/docs/mongodb-shell/write-scripts/env-variables/).
