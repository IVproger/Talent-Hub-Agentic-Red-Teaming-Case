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
  `run --profile … --dry-run` — предпросмотр кампании (5.2, US-16).
- **Цепочки шагов:** `ScenarioStep` в runner, `PlannedScenario.steps`.
  Многошаговая атака (внедрение → финализация → активация другой ролью) —
  одна попытка с одним сбросом и одним окном evidence.
- **Отчёт:** этап цепочки выводится из сработавшего предиката, находка несёт
  роли/режим/выборку, условия воспроизведения покрывают все сценарии,
  ограничения собираются детерминированно.

**Пайплайн работает end-to-end на фейках:** `run_campaign(scenarios, deps, storage)` → перебирает `PlannedScenario` → `run_scenario` → агрегирует → пишет `findings.json` + `report.md` + `status.json`. Осталось заменить фейки на реальные `adapter`/`evidence` и подать реальные `PlannedScenario` (из composer/registry).

### oushtt — готово (Фаза 0)
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

Тесты: 236 (1 пре-существующий фейл `stand.observability`).

## Контракты стыковки (ВАЖНО — согласовать)

### 1. Runner ↔ evidence (seam для bundle 3.6)

`campaign/runner.py::run_scenario` ожидает у `deps.evidence` объект с:
```python
def mark(self) -> Marker: ...
def collect_facts(self, since: Marker) -> Facts: ...   # нормализованные факты!
def reset(self) -> None: ...
```
**`collect_facts` возвращает уже `Facts`** (не `list[Observation]`) — то есть нормализация (Observation → Facts через `projection`/`principal_of`/`memdiff`) живёт **в bundle** (3.6), как в спеке §4.2.

Спек §4.2 у bundle называет методы `mark_all()`/`collect_all()->Facts`. **Нужно выровнять имена**: либо bundle экспонирует `mark`/`collect_facts`/`reset`, либо делаем тонкий шим. Предложение — bundle реализует ровно `mark`/`collect_facts`/`reset` (плюс свои `capabilities()`/`supports()` для гейта).

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

## Блокировано — ждёт oushtt

| Задача (dseredkin) | Нужен код oushtt |
|---|---|
| Wiring runner → реальный evidence | **3.6 bundle** (по seam выше) + **3.3 log_regex** (вызовы инструментов — первичный источник) |
| Исполнение `run --profile` (без `--dry-run`) | то же: без bundle собрать `RunnerDeps` нечем |
| 5.3 CLI `profile check/verify` | 3.7 calibrate (S4) |
| 4.4 удаление старого · перевод `scenario.py` | big-bang — когда новый путь заменит старый |

Готово и разблокировано: 1.2 registry, 1.3 diff, 2.2–2.4 адаптер и личности,
3.2 `db_query`. Адресация `--profile name@version` уже поверх реестра.

## Следующие шаги

1. ~~Источник `PlannedScenario`~~ — готово: `campaign/scenarios.py` + каталог `scenarios/v2/`.
2. ~~CLI-предпросмотр~~ — готово: `run --profile … --dry-run` (US-16).
3. **Свести bundle к seam** (§контракты 1) — bundle 3.6 экспонирует
   `mark`/`collect_facts`→`Facts`/`reset`. **Это единственный блокер исполнения.**
   Вместе с ним нужен 3.3 `log_regex`: без источника вызовов инструментов
   вердикт по инварианту не поднимается выше `indirect`/`UNOBSERVABLE`.
4. **Собрать реальный `RunnerDeps`** в CLI: `HttpChatAdapter.from_profile(profile)`
   + bundle → снять запрет на `run --profile` без `--dry-run`.
5. **`profile check/verify`** (5.3) поверх 3.7 calibrate.
6. **Big-bang:** удалить `client.py`/`tracer.py`/`state.py`/`scorers.py`/`target_runtime.py`/`pipeline.py`, перенести ценные тест-кейсы.

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
