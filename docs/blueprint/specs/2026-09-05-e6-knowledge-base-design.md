# E6 — База знаний о проведённых атаках (спек)

> Спек эпика **E6**. Как результаты кампаний копятся в общей базе и
> становятся контекстом для следующих проверок. Плагинится в Ядро:
> потребляет `runs/<id>/` артефакты, питает дедуп (E4) и контекст (E4).
>
> Дата: 2026-09-05 · Команда: Zero Trace · Продукт: MOROK

## Цель

Чтобы знания обо всех проведённых атаках не терялись внутри отдельной
кампании, а копились в общей базе по агенту (US-19) — для истории проверок,
дедупа (US-14) и переиспользования контекста (US-21).

## Спек-источник

Ядро: `runs/` storage, findings. E4: dedup/context. Бэклог: US-19 (+ питает US-14, US-21).

## Global Constraints (в дополнение к Ядру)

- **База — производна от `runs/`.** Каждая запись ссылается на исходную кампанию и её след; `runs/` остаётся источником истины и иммутабелен. Переналивка базы из `runs/` возможна в любой момент.
- **Без внешних зависимостей.** `sqlite3` из stdlib.
- **Только детерминированные факты** (payload, роли, verdict, evidence-ссылки, версия агента) — не проза отчёта.

---

## 1. Что хранится (US-19 AC1)

Запись на **атаку** (попытку с payload'ом):

| Поле | Источник |
|---|---|
| `id`, `campaign_run_id` | run-артефакты |
| `profile_name`, `profile_version` | `campaign.json` |
| `scenario_id`, `attack_class`, `standard_refs` | сценарий |
| `payload`, `payload_tokens` | `knowledge.jsonl` (токены — для дедупа) |
| `roles` (attacker/victim принципалы), `mode` | attempt |
| `verdict`, `severity`, `compromise_point`, `chain_stage` | findings |
| `evidence_refs` (trace-id/observation-id) | observability |
| `created_at` | время прогона |

## 2. Хранилище (`knowledge/store.py`)

`sqlite3`, файл `knowledge.db` (вне `runs/`, общий по установке):

```sql
CREATE TABLE attacks (
  id TEXT PRIMARY KEY,
  campaign_run_id TEXT,
  profile_name TEXT, profile_version TEXT,
  scenario_id TEXT, attack_class TEXT, standard_refs TEXT,
  payload TEXT, payload_tokens TEXT,
  roles TEXT, mode TEXT,
  verdict TEXT, severity TEXT, compromise_point TEXT, chain_stage TEXT,
  evidence_refs TEXT, created_at TEXT
);
CREATE INDEX ix_profile ON attacks(profile_name, profile_version);
```

Запись связывается с исходными trace/run артефактами (US-19 AC2). Результаты
разных кампаний по одному агенту доступны в одном репозитории (US-19 AC3).

## 3. Наполнение

- **Runner** после кампании пишет каждую попытку в базу (append), не трогая `runs/`.
- **Baseline** (E4 §5) — тоже источник наполнения (US-19 AC3).
- **Реиндексация:** `morok kb rebuild` перечитывает `runs/*/` и пересобирает базу (idempotent).

## 4. Как база питает генерацию

- **Дедуп (US-14):** `is_duplicate(candidate, prior)` — `prior` берётся из `attacks.payload` по этому профилю (E4 §7).
- **Контекст (US-21):** `context.py` строит сводку «что подтверждалось / что не давало эффекта / где обрывалась цепочка» из `verdict`/`chain_stage` по профилю (E4 §8).

## 5. Область базы — открытый вопрос

По бэклогу (открытый вопрос №3): в пределах одного агента, всех агентов
организации или переносимая библиотека между установками. Спек по умолчанию —
**по агенту** (`profile_name`); индекс это позволяет; расширение до
организации — фильтр по набору профилей, до библиотеки — экспорт/импорт базы.
Решение — за продуктовым владельцем; интерфейс не блокирует ни один вариант.

## 6. CLI

```
morok kb list                 # атаки по профилю
morok kb search --contains X  # поиск по payload/классу
morok kb rebuild              # переналить из runs/
```

## 7. Модули и интерфейсы

```
knowledge/store.py    # sqlite CRUD + реиндексация
knowledge/query.py    # выборки для дедупа/контекста/CLI
```

```python
class KnowledgeStore(path):
    def record(self, attack: dict) -> None: ...
    def payloads_for(self, profile_name: str) -> list[str]: ...   # → дедуп
    def context_for(self, profile_name: str) -> dict: ...         # → генератор
    def rebuild_from_runs(self, runs_root: Path) -> int: ...
```

## 8. Трассируемость (E6 → US)

| Механизм | US |
|---|---|
| Единая база, поля атаки, ссылка на кампанию/след, кросс-кампания | US-19 |
| `payloads_for` → дедуп | US-14 |
| `context_for` → генератор | US-21 |
