# STATUS — прогресс реализации Ядра

> Живой снимок: что готово, что блокировано, и **контракты стыковки** между
> dseredkin и oushtt. Обновлять при каждом слиянии в `main`.
>
> Обновлено: 2026-09-05

## Что в `main`

### dseredkin — готово (14 задач + оркестрация)
- **Фаза 0:** `tests/fakes.py`, `normalize/facts.py`, `assertions/verdict.py`
- **S1 core-logic:** `normalize/memdiff.py`, `normalize/projection.py`, `assertions/predicates.py`, `assertions/registry.py`, `assertions/dispatch.py`, `tests/test_no_target_leak.py`
- **S5:** `storage/runs.py` (4.1), `campaign/plan.py` (4.2), `campaign/runner.py` (4.3), `campaign/orchestrator.py` (`run_campaign` + `build_findings` + `PlannedScenario`)
- **S7:** телеметрия в runner fail-open (6.2), `reporting/technical.py` (6.3)

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

Тесты: 161 (1 пре-существующий фейл `stand.observability`).

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
`adapter.open_session(role, session_id, mode)` → session; `session.send(msg)->str`; `session.commit_memory()`. Роль актора в runner сейчас — `"attacker"`.

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
| Wiring runner → реальный evidence | 3.6 bundle (по seam выше) + 3.2–3.7 провайдеры (S4) |
| 5.2 CLI `run` | 1.2 profile registry (S2) + 2.4 http_chat (S3) |
| 5.3 CLI `profile` | 3.7 calibrate (S4) |
| 4.4 удаление старого · 5.1 rewrite scenario | big-bang — когда новый путь заменит старый |

## Следующие шаги (когда S3/S4/1.2 в `main`)

`run_campaign` уже написан и работает на фейках — интеграция сводится к замене фейков реальными компонентами:

1. **Свести bundle к seam** (§контракты 1) — bundle 3.6 экспонирует `mark`/`collect_facts`→`Facts`/`reset` (или тонкий шим).
2. **Источник `PlannedScenario`**: composer (E4) или загрузчик встроенных сценариев на новом словаре → `id/attack_class/standard_refs/actor/payloads/goal/boundary`.
3. **Собрать реальный `RunnerDeps`**: `adapter` (2.4 http_chat через registry 1.2) + `evidence` (bundle 3.6) → передать в `run_campaign`.
4. **CLI** `run --profile` / `profile check` поверх этого (5.2/5.3).
5. **Big-bang:** удалить `client.py`/`tracer.py`/`state.py`/`scorers.py`/`target_runtime.py`/`pipeline.py`, перенести ценные тест-кейсы.
