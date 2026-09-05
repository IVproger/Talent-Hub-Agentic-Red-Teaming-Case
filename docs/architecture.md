# Runtime architecture

## Supported path

> Этот раздел описывает действующий (старый) путь исполнения. Новое ядро
> — ниже, в разделе «Ядро: профиль → факты → вердикт»; старый путь удаляется
> целиком, когда новый его заменит.

Both the CLI and Streamlit UI call `agentic_redteam.pipeline.run_pipeline`.
Adaptive BAC and bundled YAML scenarios share target preflight, state evidence,
deterministic scoring, report generation, telemetry and per-run storage.

```text
config/target.yaml
        |
        +--> stand sync --> stand/.env --> agent-api
        |
        +--> doctor (read only)
        |
        +--> CLI / UI --> pipeline --> runs/<run-id>/
                                |
                                +--> agent-api --> ReAct/tools/memory
                                |
                                +--> deterministic verdict
```

`config/target.yaml` owns non-secret model/provider settings. `stand/.env` owns
credentials and operational limits. The sync command projects the YAML target
model into the three stand variables required by its current implementation.

## Evidence boundary

The runner captures memory snapshots and the invest-server access log around an
attempt. Scorers consume that state, never the natural-language answer or a
Langfuse trace. This keeps verdicts reproducible when report generation or
telemetry is unavailable.

The access log is currently global to the isolated local stand. Do not mix
unrelated traffic with a run until the stand emits a run/session correlation ID
in its audit events.

## Distributed tracing

When enabled, the runner starts `redteam.run` and injects W3C trace context into
the two target endpoints. The stand only instruments requests with a
`traceparent`, continues the same OpenTelemetry context, and adds observations
for target LLM calls, tools and memory orchestration. Both sides use one
Langfuse project; `component` metadata distinguishes `redteam-runner` from
`target-stand`, while `agent_role` distinguishes `attacker`, `target` and
`report_writer` observations.

All telemetry is optional and fail-open. Capture is redacted and bounded before
export. The local artifact manifest is the correlation record between the trace
and the deterministic run.

## Ядро: профиль → факты → вердикт

Три слоя, зависимость строго в одну сторону. Подробные спеки и диаграммы —
в [`docs/blueprint/`](blueprint/); здесь только форма.

```text
профиль (profiles/<name>/<version>.yaml)
   |  единственный носитель знания о цели
   v
граница цели ── адаптер (adapters/) · личности · evidence-провайдеры (evidence/)
   |  Observation — сырые наблюдения источников
   v
ядро ── normalize/ (факты) → assertions/ (предикаты) → campaign/ (вердикт, runner)
   |  о цели не знает: оперирует принципалами и фактами, не именами полей
   v
runs/<run-id>/ — campaign.json, transcript.jsonl, findings.json, report.md
```

**Вердикт выносится только по состоянию.** Предикат на тексте ответа получает
градацию `TEXT` и опускает потолок вердикта до `indirect`. Вызовы инструментов —
первичный источник, память — усилитель: без источника вызовов вердикт не
поднимается выше `indirect`/`UNOBSERVABLE`, но никогда не становится «успехом».

Градации предиката: `STATE` (доказано состоянием), `TEXT` (только текст),
`UNOBSERVABLE` (нужного факта на этой цели не видно), `ERROR` (техническая
ошибка). Вердикт попытки: `proven` · `indirect` · `not_proven` · `error`.
Ошибочные попытки в знаменатель ASR не входят.

**Что даёт разделение.** Один и тот же сценарий идёт на разные цели без правки
ядра: меняется профиль. Обратная сторона — на цели без нужного источника
сценарий недоказуем, и `profile coverage` говорит об этом заранее, сверяя
объявленные профилем источники с требованиями предикатов.

**Наблюдаемость прогона fail-open, evidence — нет.** Langfuse как телеметрия
не влияет на вердикт; Langfuse или OTel как источник evidence load-bearing:
отказ источника даёт `error`, а не пустой успешный результат.
