# STATUS — прогресс реализации Ядра

> Живой снимок: что готово, что блокировано, и **контракты стыковки** между
> dseredkin и oushtt. Обновлять при каждом слиянии в `main`.
>
> Обновлено: 2026-09-05

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
  одна попытка с одним сбросом и одним окном evidence.
- **Отчёт:** этап цепочки выводится из сработавшего предиката, находка несёт
  роли/режим/выборку, условия воспроизведения покрывают все сценарии,
  ограничения собираются детерминированно.

**Пайплайн работает end-to-end на фейках:** `run_campaign(scenarios, deps, storage)` → перебирает `PlannedScenario` → `run_scenario` → агрегирует → пишет `findings.json` + `report.md` + `status.json`. Осталось заменить фейки на реальные `adapter`/`evidence` и подать реальные `PlannedScenario` (из composer/registry).

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

Тесты: 304 (1 пре-существующий фейл `stand.observability`).

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
| 4.4 big-bang: удаление старого pipeline | не начат — новый путь заменил старый, можно приступать |
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
7. **Big-bang** (4.4): удалить `client.py`/`tracer.py`/`state.py`/`scorers.py`/
   `target_runtime.py`/`pipeline.py`, схлопнуть `scenarios/v2/` в `scenarios/`,
   перенести ценные тест-кейсы.
8. **Порт UI** (5.4) на `run_campaign`.

## Временное, что переедет

- `PROVIDER_KINDS` в `app_cli.py` (имя плагина → `EvidenceKind`) — CLI как
  composition root связывает имена, пока нет реестра провайдеров бандла (3.6).
  Нужен для `profile coverage`; переезжает в 3.6.
- Каталог `agentic_redteam/scenarios/v2/` схлопывается в `scenarios/`, когда
  старый `scenario.py` уйдёт при big-bang.
- При удалении `target_runtime.py` (4.4) сохранить проверки модели, которыми
  пользуется `stand_sync` — перенести в модуль bootstrap.

### Границы проверки oushtt

Полный набор из 306 тестов зелёный. На живом стенде проверены HTTP-адаптер,
mint, Mongo, log-regex, reset, `profile check/verify` и BAC-кампания в двух режимах.
Модель цели — OpenRouter `qwen/qwen3-8b`; запросы к ней реально выполнялись.
Canary ранее проверен локальным HTTP; Langfuse/OTLP проверены через fake readers.
Исправлен обнаруженный пробел: runner сохраняет независимую копию facts/raw
observations каждой попытки, orchestration пишет `evidence-NNNN.json`,
transcript и находки ссылаются на соответствующий файл.

## Расхождения со спеком (решить)

- **ASR.** Спек §6: «доля `proven` по **сценариям**». Считается по **попыткам**
  (`proven / (proven + not_proven)`), и `indirect` не попадает в знаменатель, хотя
  инвариант выводит из него только `error`. Не менял: `ui/app.py` показывает
  `asr_percent` вместе с `attempts_scored`. Заголовок в отчёте приведён к факту
  («ASR по попыткам»).
- **Усилители в `goal`.** Плана 5.1 требует помечать `memory_write` в
  `poison-to-tool-chain` как необязательный усилитель, но ни в словаре предикатов,
  ни в `verdict()` нет признака «необязательный». Сейчас предикат обязателен.
- **`reset_policy: per_step`** каталогом не используется и в runner не реализован
  (сброс идёт раз на попытку).
- **Атрибуция многошаговых цепочек:** runner пока собирает одно окно facts на
  всю цепочку и сравнивает с актором сценария. Привязка `at` к отдельному шагу
  и его принципалу не реализована; BAC с одним актором этим не затронут.
  Перед подтверждением `poison-to-tool-chain` нужно устранить это расхождение.
