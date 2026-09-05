# Разделение работы — dseredkin ↔ Tamerlan

> Кто какие задачи Ядра берёт. Задачи — из [`morok-core-plan`](2026-09-05-morok-core-plan.md);
> обоснование потоков и правила независимости — в [`task-assignment`](task-assignment.md).
>
> Дата: 2026-09-05 · Команда: Zero Trace

## Исполнители

| Инженер | GitHub | Зона |
|---|---|---|
| Даниил Середкин | `dseredkin` | ядро (логика), runner, CLI/UI, отчёт, наблюдаемость |
| Тамерлан | `oushtamer` *(подтвердить)* | профиль, адаптер, evidence-провайдеры, llm, стенд |

Иван Голов (`Ivan Golov`) — продукт (шаблоны E3, бизнес-отчёт E9), вне этого code-split.

---

## dseredkin — задачи

| Задача | Что | Поток |
|---|---|---|
| **0.0** | фейки (FakeAdapter/Evidence/LLM/Runner) | Фаза 0 |
| **0.1** | модели фактов (Facts, ObservedToolCall/…) | Фаза 0 |
| **0.2** | вердикт (Grade, CheckOutcome, `verdict()`) | Фаза 0 |
| **0.3** | диф памяти (`memdiff`) | S1 core-logic |
| **0.4** | проекция записей (`projection`) | S1 core-logic |
| **0.5** | предикаты (`predicates`) | S1 core-logic |
| **0.6** | реестр требований (`registry`) | S1 core-logic |
| **0.7** | grep-страж target-независимости | S1 core-logic |
| **4.1** | storage (`RunStorage` + campaign/transcript) | S5 runner |
| **4.2** | план кампании (`Campaign`, порядок) | S5 runner |
| **4.3** | единый runner (`run_campaign`) | S5 runner |
| **4.4** | удаление старого pipeline | S5 runner |
| **5.1** | модель сценария (новый словарь, reset_policy) | S6 CLI |
| **5.2** | CLI `run`/`doctor` | S6 CLI |
| **5.3** | CLI `profile`-подкоманды | S6 CLI |
| **5.4** | порт Streamlit-UI | S6 CLI |
| **5.5** | документация (README/architecture) | S6 CLI |
| **6.2** | перенос `observability.py` + wire в runner | S7 |
| **6.3** | `reporting/technical.py` — отчёт | S7 |

**Итого: 19 задач.** Каталоги: `normalize/` `assertions/` `campaign/` `storage/` `app_cli.py` `ui/app.py` `scenarios/` `observability.py` `reporting/`.

---

## oushtamer (Tamerlan) — задачи

| Задача | Что | Поток |
|---|---|---|
| **1.1** | схема профиля (`TargetProfile`, ToolDecl/…) | Фаза 0 |
| **2.1** | протоколы адаптера (`TargetAdapter`, Principal…) | Фаза 0 |
| **3.1** | протоколы evidence (`EvidenceProvider`, Kind…) | Фаза 0 |
| **1.2** | реестр профилей (`profiles/<name>/<ver>.yaml`) | S2 profile |
| **1.3** | диф версий профиля | S2 profile |
| **2.2** | личности `static` | S3 adapter |
| **2.3** | личности `docker_exec_mint` (порт mint_key) | S3 adapter |
| **2.4** | `http_chat` адаптер | S3 adapter |
| **3.2** | провайдер `db_query` (Mongo) | S4 evidence |
| **3.3** | провайдер `log_regex` (tool calls) | S4 evidence |
| **3.4** | провайдер `http_canary` | S4 evidence |
| **3.5** | провайдер `trace` (Langfuse/OTLP) | S4 evidence |
| **3.6** | `bundle` + capability-гейт | S4 evidence |
| **3.7** | калибровка `check`/`verify` | S4 evidence |
| **6.1** | перенос `llm.py` + reshape ролей | S7 |
| **6.4** | `stand sync` + bootstrap-профиль стенда | S7 |

**Итого: 16 задач.** Каталоги: `profile/` `adapters/` `evidence/` `llm.py` `stand_sync.py`.

---

## Порядок и точка синхронизации

```
Фаза 0 (оба, ПЕРВЫМ делом, параллельно):
   dseredkin: 0.0 0.1 0.2        oushtamer: 1.1 2.1 3.1
        │                              │
Фаза 1 (параллельно, независимо):
   dseredkin: S1 (0.3–0.7)       oushtamer: S2 (1.2–1.3) · S3 (2.2–2.4) · S4 (3.2–3.7)
        └──────────────┬───────────────┘
Точка сборки — S5 runner (dseredkin, 4.1–4.4): нужны и ядро, и профиль/адаптер/evidence.
        │
Фаза 3 (параллельно):
   dseredkin: S6 (5.1–5.5) · 6.2 · 6.3      oushtamer: 6.1 · 6.4
```

**Главное:**
- **Фаза 0 — первой** у обоих: замораживает контракты (`facts`/`verdict` у dseredkin, `TargetProfile`/`TargetAdapter`/`EvidenceProvider` у oushtamer). Пока не готова — Фаза 1 не начинается.
- **S5 runner (dseredkin)** ждёт, пока oushtamer закроет S2/S3/S4 — это единственная жёсткая межчеловеческая зависимость.
- До runner'а оба работают в **разных каталогах** → не сталкиваются (правила независимости — `task-assignment.md` §8).

## Баланс

| | Задач | Роль |
|---|---|---|
| dseredkin | 19 | ядро + оркестрация (шире, т.к. держит runner/CLI/инварианты) |
| oushtamer | 16 | граница цели + данные (глубже по интеграциям) |

Свап возможен: интерфейс между потоками фиксирован Фазой 0, так что перекинуть, например, S4 evidence на отдельного агента — без изменений контракта.
