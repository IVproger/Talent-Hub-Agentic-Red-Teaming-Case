# Evidence: настройка границы цели

Источники возвращают `Observation`; `EvidenceBundle` отвечает за преобразование
в `Facts`. Ошибка чтения обязательного источника должна доходить до runner как
ошибка попытки. Это отдельный путь от fail-open телеметрии нашего запуска.

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
