# STATUS — прогресс реализации Ядра

> Живой снимок: что готово, что блокировано, и **контракты стыковки** между
> dseredkin и oushtt. Обновлять при каждом слиянии в `main`.
>
> Обновлено: 2026-09-05

## Актуальное дополнение: E8 + сквозное (dseredkin, поверх `b40c513`)

Закрыты последние незакрытые куски зоны dseredkin. **441 тест, весь набор
зелёный** — включая `stand.observability`, который висел красным всё это время.

**Тот фейл не был дефектом кода.** В `.venv` стоял langfuse `2.60.10`, тогда как
`requirements.txt` требует `>=4.8.1,<5`. Opentelemetry приходит транзитивно
только с langfuse 3+, поэтому в `stand/app/observability.py` падал
`from opentelemetry...`, а широкий `except Exception` (fail-open) превращал это
в «трейс не начат» — тест видел пустой список. Лечится
`pip install -r requirements.txt`, код стенда трогать не пришлось.

**Важнее теста:** наш собственный `agentic_redteam/observability.py` написан под
тот же v4 API (`base_url=`, `start_as_current_observation`), которого в langfuse 2
нет. То есть на устаревшем venv телеметрия прогонов **молча не работала** —
fail-open по замыслу не роняет вердикт, но и не сообщает о несовместимости
версии. Если наблюдаемость «просто пустая» — сначала проверьте версию langfuse.

- **E8 регрессия (US-28/29).** `reporting/regression.py::compare(before, after)`
  → `RegressionDiff{per_attack, asr_before, asr_after, smoke_ok}`; значения
  `closed`/`remained`/`appeared` (русский — только на выводе). Понижение
  `proven`→`indirect` считается `remained`, а не закрытием.
- **`run --from` теперь исполняется**, а не только показывает предпросмотр.
  Повтор пишет новый `runs/<id>/` и кладёт в кампанию `replay_of` —
  исходные артефакты неизменны (US-29 AC4).
  Попутно починена точность повтора: `_planned_from_saved` **терял**
  `expect`/`remediation`, поэтому штатный сценарий при повторе переставал быть
  штатным.
- **CLI `regress export|compare`.** Набор — обычная сохранённая кампания
  (`campaign.json` + `source_runs`), поэтому исполняется тем же `run --from`;
  второго пути исполнения не заводил. `regress run --set` из спека §5 намеренно
  не делал — это был бы алиас к `run --from`.
- **US-34 авторизация.** `campaign/authorization.py`: блок `authorization`
  (`authorized_by`, `scope`, `until`) обязателен, просроченное окно = отказ.
  Гейт стоит только на пути исполнения (предпросмотр цель не трогает),
  разрешение едет в `campaign.json`. Блок добавлен в `config/target.yaml`.
- **US-35 режим без записи.** `run --read-only` + `_gate_read_only`: сценарий,
  объявляющий запись (шаг с payload, `commit_memory`, `reset_policy != none`),
  пропускается; не осталось наблюдательных — отказ. Гейт стоит **первым** в
  `execute_campaign`, до подъёма провайдеров и адаптера, поэтому CLI и UI
  ведут себя одинаково и цель не трогается. Флаг едет в `campaign.json`.
  **Граница режима:** запрещается объявленное планом, а не всё, что цель может
  записать сама в ответ на обычное сообщение — из плана это не видно, и
  обещать обратное значило бы переобещать.
- **US-13 разнообразие.** `diversity` в `findings.json` (сценарии, классы,
  пункты стандарта, число различных payload'ов, инструменты/хранилища/границы)
  и раздел «Покрытие и разнообразие» в отчёте рядом с ASR. Ошибочные попытки
  поверхность не покрывают.
- **US-36 судьба находки.** `status` + `status_history` в `knowledge.db`,
  `set_status/get/status_history`, CLI `kb status <id> [--set …] [--note …]`.
  Прогон даёт `confirmed`; реиндексация `runs/` статус **не сбрасывает**.
  Старая база мигрируется `ALTER TABLE` (проверено на реальной, 54 записи).
- **Дыра в US-34 закрыта.** Гейт авторизации стоял в `_execute_campaign`, то
  есть только на пути CLI, — а `ui/app.py` зовёт `execute_campaign` напрямую и
  запускал кампанию **вообще без рамки**. Перенёс проверку в общее ядро
  запуска (туда же, где read-only), CLI и UI передают разрешение параметром.
  Инвариант «одно ядро на оба входа» (US-07 AC3) теперь распространяется и на
  безопасность, а не только на сборку зависимостей.
- **`PROVIDER_KINDS` дедуплицирован:** был определён дважды, байт-в-байт, в
  `app_cli.py` и `generation/composer.py`. Осталось одно определение в
  `composer.py` (CLI импортирует; обратное направление дало бы цикл — CLI уже
  импортирует `generation.generator`). Пометка «переезжает в бандл (3.6)»
  сохранена.
- **Дубликат в `app_cli.py` удалён:** 8 определений (`execute_campaign`,
  `_execute_campaign`, `_gate_scenarios`, `_require_adapter_features`,
  `_require_reset_source`, `telemetry_from_config`, `reporter_from_config`,
  `new_run_id`) были продублированы байт-в-байт с `7fd282f`; второй блок молча
  перекрывал первый. −141 строка, поведение не менялось.

### Пересечение зон — требует синхронизации

`implementation-1-4-2026-09-05.md` заявляет следующими шагами oushtt «CLI:
исполнение replay… пересборка отчёта… единый путь запуска; UI поверх того же
плана». По `work-split.md` это **S6 CLI+UI — зона dseredkin**, и replay уже
сделан здесь. Прежде чем брать CLI/UI, сверьтесь: иначе получим две реализации
одного пути. Ядро (`orchestrator`/`runner`/`reporting`/`storage`) тоже правилось
из обеих зон.

## Актуальное дополнение: надёжность и метрики

Интеграция поверх `6d1d42a`: попытки сохраняются сразу, прерывание не теряет
завершённые попытки текущего сценария. ASR учитывает `indirect`, разрезы
сценарий/режим отделены от ASR по попыткам. `optional` и `per_step` реализованы
в runner; перенос UI/CLI и генерации из командной main сохранён.
Подробные контракты и дальнейшие шаги: [реализация 1–4](implementation-1-4-2026-09-05.md).

Ниже — исторические записи; актуальные изменения выше имеют приоритет.

## Что в `main`

### dseredkin — готово (14 задач + оркестрация + каталог/CLI-предпросмотр)
- **Фаза 0:** `tests/fakes.py`, `normalize/facts.py`, `assertions/verdict.py`
- **S1 core-logic:** `normalize/memdiff.py`, `normalize/projection.py`, `assertions/predicates.py`, `assertions/registry.py`, `assertions/dispatch.py`, `tests/test_no_target_leak.py`
- **S5:** `storage/runs.py` (4.1), `campaign/plan.py` (4.2), `campaign/runner.py` (4.3), `campaign/orchestrator.py` (`run_campaign` + `build_findings` + `PlannedScenario`)
- **S7:** телеметрия в runner fail-open (6.2), `reporting/technical.py` (6.3)
- **S6 (частично):** `campaign/scenarios.py` — загрузчик каталога на новом
  словаре (5.1 в новом модуле, старый `scenario.py` не тронут);
  `agentic_redteam/scenarios/v2/` — четыре встроенных сценария как данные;
  `run --profile … --dry-run` — предпросмотр кампании (5.2, US-16),
  `run --from runs/<id>` — повтор сохранённой кампании (US-29),
  `profile list/show/diff/coverage` (5.3 без `check`/`verify`),
  документация README/architecture (5.5).
- **Артефакты прогона:** `campaign.json` (пишется до исполнения) и
  `transcript.jsonl` (строка на попытку) — спек §6; `run_campaign` принимает
  `trials` и пишет их в кампанию, поэтому повтор точный.
- **Гейт покрытия (US-04):** `profile coverage` сверяет источники профиля с
  `assertions/registry.required_kinds` и до прогона говорит, где вердикт
  упрётся в `indirect` или в отсутствие источника.
- **Цепочки шагов:** `ScenarioStep` в runner, `PlannedScenario.steps`.
  Многошаговая атака (внедрение → финализация → активация другой ролью) —
  одна попытка с одним сбросом и отдельным окном evidence на каждый шаг.
- **Отчёт:** этап цепочки выводится из сработавшего предиката, находка несёт
  роли/режим/выборку, условия воспроизведения покрывают все сценарии,
  ограничения собираются детерминированно.

**Пайплайн собран:** `run_campaign(scenarios, deps, storage)` → перебирает `PlannedScenario` → `run_scenario` → агрегирует → пишет `findings.json` + `report.md` + `status.json`. CLI уже подключает реальные adapter/evidence и PlannedScenario; результаты живых проверок — ниже.

### oushtt — готово (16 из 16 задач)
- `adapters/base.py` (2.1), `evidence/base.py` (3.1), `profile/schema.py` (1.1), `errors.py`
- фикстуры: `tests/data/profile_stand.yaml`, `profile_dvaa.yaml`
- **1.2:** файловый `ProfileRegistry` (`list/load/save`), неизменяемые версии,
  bootstrap `profiles/genai-invest-stand/1.0.0.yaml`.
- **1.3:** `profile.diff.diff(a, b)` — `tools/roles/entrypoint/memory`,
  `added/removed` как словари, `changed` с `before/after`; пустой диф — `{}`.
- **2.2:** `Credential`, `IdentityProvider`, `StaticIdentityProvider`; runtime-секрет
  через `identities.credential.secret_env`, шаблоны `{principal}/{role}/{secret}`.
- **2.3:** `DockerExecMintProvider(identities, runner)` — перенос mint без
  зависимости от `client.py`; compose/service из профиля, stdout с ключом не выводится в ошибках.
- **2.4:** `HttpChatAdapter(profile, identities, transport=None)` и
  `HttpChatAdapter.from_profile(profile)`. `entrypoint.preflight.path` проверяется GET
  без mint. `per_deployment` требует переданный `mode_switcher(mode, declaration)`.
- **3.2:** `DbQueryProvider(config, runner)` — Mongo через mongosh (локально/Compose),
  payload `{store_id, documents, record, scope}`, read-only калибровка; пустая коллекция
  означает неподтверждённую привязку. `uri_env` необязателен для локального Compose Mongo.
- **3.3:** `LogRegexProvider(config, runner)` — Docker/file/cli-json, курсор с
  проверкой целостности префикса; read-only calibration по `calibration.expected_principal`.
- **3.4:** `HttpCanaryProvider(config)`, `bind_addr`, `url_for(token)`, `close()`;
  callbacks возвращаются как `Observation`, преобразование в `ObservedCallback` — в bundle.
- **3.5:** `TraceProvider`, `LangfuseReader` (Observations API v2/v1), `OtelJsonReader`;
  параметры и корреляция описаны в [evidence integration](oushtt-evidence-integration.md).
- **3.6:** `EvidenceBundle.from_profile(profile)` собирает провайдеры, предоставляет
  `mark/collect_facts/reset` и алиасы `mark_all/collect_all`, нормализует наблюдения.
  Добавлены `StateResetProvider` с явной областью очистки и JSON-file память для DVAA.
  Отсутствие reset-провайдера требует `reset_policy=none`, а не молчаливого no-op.
- **3.7:** `evidence.calibrate.check(bundle, adapter)` (read-only) и `verify`
  (проба с очисткой): видимость проверяется через реальный метод памяти цели,
  объявленный в `read.config.visibility`, а не ответ LLM или метку `scope`.

- **6.1:** LLM-роли `attack_generator/report_writer/analyst`; модель цели —
  `entrypoint.target_model` bootstrap-профиля, ссылка `target.profile` в config.
  Старые pipeline/doctor/UI адаптированы к отдельной модели цели; сохранённый
  config прогона содержит отдельный `target_model`, только три роли в `llm`.
  Для программного legacy RunConfig без ссылки на профиль оставлен прежний
  default Ollama; `stand sync` всегда требует явный профиль.
- **6.4:** `stand sync` обозначен в модуле и README как отдельная настройка
  нашего стенда. Bootstrap составлен вручную; OpenAPI необязателен.
  При удалении старого `target_runtime.py` нужно сохранить используемые
  `stand_sync` проверки модели в модуле bootstrap (задача 4.4).

Тесты: 302 (1 пре-существующий фейл `stand.observability`).

## Контракты стыковки (ВАЖНО — согласовать)

### 1. Runner ↔ evidence (seam для bundle 3.6)

`campaign/runner.py::run_scenario` ожидает у `deps.evidence` объект с:
```python
def mark(self) -> Marker: ...
def collect_facts(self, since: Marker) -> Facts: ...   # нормализованные факты!
def reset(self) -> None: ...
```
**`collect_facts` возвращает уже `Facts`** (не `list[Observation]`) — то есть нормализация (Observation → Facts через `projection`/`principal_of`/`memdiff`) живёт **в bundle** (3.6), как в спеке §4.2.

Bundle реализует `mark`/`collect_facts`/`reset`, а также `mark_all`/`collect_all`
как алиасы. Оба варианта используют непрозрачный одноразовый `Marker`.
`capabilities()`/`supports(goal)` доступны для preflight-гейта.

**Обновление атрибуции:** runner вызывает `mark → действие → collect_facts`
на **каждом шаге**, включая finalize. Новый `StepEvidence` содержит фактический
`session.principal.value`, session_id, facts и raw observations. Протоколы Facts,
TargetAdapter и EvidenceBundle не изменены. FakeEvidenceSource теперь должен
давать по одному Facts на шаг, а не на всю попытку. Подробности и живой прогон:
[step-attribution-2026-09-05](step-attribution-2026-09-05.md).

### 2. Runner ↔ adapter (уже совпадает)

Runner использует замороженный `TargetAdapter` (2.1):
`adapter.open_session(role, session_id, mode)` → session; `session.send(msg)->str`; `session.commit_memory()`.
**Роль берётся из шага цепочки** (`ScenarioStep.actor`), а не константа `"attacker"`:
каждый актор держит одну сессию на свои шаги, поэтому `commit_memory` попадает
в ту же сессию, что и внедрение.

### 2a. Сценарий → runner

`campaign/scenarios.py::ScenarioSpec.to_planned(principals)` отдаёт
`PlannedScenario`. `principals` — отображение «роль сценария → значение
принципала»; собирает его CLI из профиля (`identities.principal.attribute`,
иначе атрибут первой границы изоляции) — сам каталог о цели не знает.

### 3. RunnerDeps
```python
RunnerDeps(adapter, evidence, id_factory=None, now=None, telemetry=None)
```

### 4. Goal-ассершены (словарь предикатов)
`assertions/dispatch.py::evaluate(assertion, facts, actor)` принимает dict вида
`{"type": "tool_principal_mismatch", "at": ...}` и т.д. Типы: `tool_principal_mismatch`,
`tool_principal_equals`, `memory_write`, `isolation_violation`, `cross_session_effect`,
`external_callback`, `response_contains`. Их и должен генерить composer (E3/E4).

## Интеграция — зависимости oushtt готовы

| Задача (dseredkin) | Нужен код oushtt |
|---|---|
| Wiring runner → реальный evidence | ✅ сделано |
| Исполнение `run --profile` | ✅ сделано: `HttpChatAdapter.from_profile` + `EvidenceBundle.from_profile` → `RunnerDeps` |
| 5.3 CLI `profile check/verify` · `doctor --profile` | ✅ сделано поверх `evidence.calibrate` |
| 5.4 порт Streamlit-UI | не начат (в `ui/app.py` незакоммиченная работа) |
| 4.4 big-bang: удаление старого pipeline | ✅ сделано |
| `run --from` с исполнением (реплей) | пока только предпросмотр |
| 4.4 удаление старого · перевод `scenario.py` | big-bang — когда новый путь заменит старый |

Готово и разблокировано: 1.2 registry, 1.3 diff, 2.2–2.4 адаптер и личности,
3.2 `db_query`, 3.3 `log_regex` (вызовы инструментов — первичный источник),
3.4 `http_canary`, 3.5 `trace`, 3.6 `bundle`, 3.7 `calibrate`, 6.1 роли, 6.4 bootstrap.
**S2/S3/S4 закрыты, пайплайн собран end-to-end на реальных компонентах.**

## Следующие шаги

1. ~~Источник `PlannedScenario`~~ — готово: `campaign/scenarios.py` + каталог `scenarios/v2/`.
2. ~~CLI-предпросмотр~~ — готово: `run --profile … --dry-run` (US-16).
3. ~~Свести bundle к seam~~ — готово (§контракты 1): bundle экспонирует
   `mark`/`collect_facts`→`Facts`/`reset` и сам нормализует `Observation`
   провайдеров. Имена совпали, шим не понадобился.
4. ~~Собрать реальный `RunnerDeps`~~ — готово, `run --profile` исполняется.
5. ~~`profile check/verify`~~ — готово.
6. **Живой стенд:** `profile check/verify` и BAC в двух режимах прошли;
   [протокол проверки](live-validation-2026-09-05.md).
   Многошаговые сценарии и UI требуют отдельного живого прогона.
7. ~~Big-bang~~ (4.4) — сделано. `target_runtime.py` **оставлен**: он держит
   `stand sync` и `doctor`, а не старый прогон.
8. ~~Порт UI~~ (5.4) — сделано.
9. ~~Вернуть генерацию payload'ов~~ — сделано: эпик E3/E4 закрыт (`generation/`
   templates→composer→coverage→baseline + dedup→generator→context), флаг
   `run --generate N` в CLI. В origin (`128470e..6d1d42a`).
10. **Живой прогон многошаговых сценариев и UI** — на стенде не гонялись.
    Блокер снят (привязка evidence к шагу), на фейках цепочка даёт `proven`.
11. **Сквозная трасса** — адаптер не пробрасывает W3C `traceparent`, поэтому
    в трассе видны попытки кампании, но не ReAct-цикл внутри цели.

## Проверки, которые ловят несовместимость до прогона

Три вещи отклоняются до того, как цель тронута, а не превращаются в мусорную
статистику: непокрытый источниками сценарий (`bundle.supports`), сценарий со
сбросом на цели без `session_reset`, сценарий с шагом `commit_memory` на цели
без этой фичи. Общий принцип: если несовместимость видна из профиля и шагов,
она должна быть отказом, а не `error`/`not_proven` в каждой попытке.

## Генерация payload'ов — восстановлена (E3/E4)

Adaptive BAC из старого `pipeline.py` был удалён при big-bang, но заменён
эпиком E3/E4: `generation/generator.py` пишет N вариантов одним фиксированным
списком (LLM только текст), `run --generate N` подаёт их в кампанию. Плюс
детерминированный composer (шаблон×профиль→сценарий), карта покрытия и
замороженный baseline (`scenarios/baseline/`). Дедуп (US-14) и контекст
прошлых кампаний (US-21) реализованы как механизм; **проводка US-21 в CLI
ждёт E6** (источник истории — база знаний).

Известные хвосты E3/E4: `cus=` маркер в шаблоне утечки промпта — единственный
target-специфичный элемент, зафиксирован комментарием, полная параметризация
из профиля — follow-up мульти-таргета; дубли определений в `app_cli.py`
(пре-существуют, не из E3/E4) — вычистить отдельно.

## Временное, что переедет

- `PROVIDER_KINDS` в `app_cli.py` (имя плагина → `EvidenceKind`) — CLI как
  composition root связывает имена, пока нет реестра провайдеров бандла (3.6).
  Нужен для `profile coverage`; переезжает в 3.6.
- При удалении `target_runtime.py` (4.4) сохранить проверки модели, которыми
  пользуется `stand_sync` — перенести в модуль bootstrap.

### Границы проверки oushtt

Полный набор из 318 тестов зелёный. На живом стенде проверены HTTP-адаптер,
mint, Mongo, log-regex, reset, `profile check/verify` и BAC-кампания в двух режимах.
Модель цели — OpenRouter `qwen/qwen3-8b`; запросы к ней реально выполнялись.
Canary ранее проверен локальным HTTP; Langfuse/OTLP проверены через fake readers.
Исправлен обнаруженный пробел: runner сохраняет независимую копию facts/raw
observations каждой попытки, orchestration пишет `evidence-NNNN.json`,
transcript и находки ссылаются на соответствующий файл.

## Расхождения со спеком — закрыты

Раздел был устаревшим: три из четырёх пунктов уже исправлены в коде. Сверено
по факту, а не по памяти.

- **ASR — закрыто.** Считается по сценариям и режимам (`asr_by_mode` —
  основной разрез), `indirect` входит в знаменатель, `error` и `expect=pass`
  исключены. ASR по попыткам остался дополнительной метрикой
  (`attempt_asr_percent`). Спек §6 соблюдён.
- **Усилители в `goal` — закрыто.** `optional: true` учитывается в
  `runner.py` при сборке вердикта: такой предикат сохраняется в evidence, но
  не блокирует вердикт и не требует своего источника в capability-гейте.
- **`reset_policy: per_step` — закрыто**, реализован в `_run_chain`.
- **Атрибуция многошаговых цепочек — закрыто** (отдельное окно и principal на
  шаг). Живой прогон `poison-to-tool-chain` — по-прежнему не делался.

## Осознанно не тронуто

- `_text`/`_list` совпадают в `campaign/scenarios.py` и `generation/template.py`
  (4 строки, вся суть — звать свой `_invalid` со своим префиксом). Вынос
  потребовал бы прокидывать `_invalid` параметром — машинерии больше, чем
  дублирования. Одноимённые хелперы в `profile/schema.py` — другая сигнатура,
  не дубликат.
- `_render_surface`/`_render_preview` в `app_cli.py` и `ui/app.py` — одно имя,
  разные слои представления над **одним** источником (`surface_of`). Это и есть
  инвариант E2 «один источник — два вида», а не дублирование.
- `redact_secrets`/`sanitize_error` определены и в `errors.py`, и в
  `redaction.py` с почти одинаковыми регулярками — **настоящий дубликат**, но
  оба файла в зоне oushtt, поэтому только помечаю.
