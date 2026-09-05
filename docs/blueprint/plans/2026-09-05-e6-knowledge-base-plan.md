# E6 — База знаний о проведённых атаках: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Копить результаты всех кампаний по агенту в общей sqlite-базе, производной от `runs/`, и питать из неё дедуп (US-14) и контекст прошлых кампаний (US-21) — закрыв проводку US-21, которую E3/E4 оставил как механизм без источника.

**Architecture:** `knowledge/store.py` — sqlite CRUD + реиндексация. `knowledge/ingest.py` — чистая функция «каталог прогона → список записей-атак» из реальных артефактов (`campaign.json`/`transcript.jsonl`/`findings.json`/`observability.json`). `knowledge/query.py` — выборки `payloads_for`/`context_for` в том же виде, что уже потребляют `generation.dedup.is_duplicate` и `generation.generator.generate`. CLI (`kb list/search/rebuild`) и проводка: после кампании CLI пишет прогон в базу, а `run --generate` берёт prior из базы.

**Tech Stack:** Python 3.12 (stdlib: `sqlite3`, `json`, `pathlib`, `dataclasses`), `unittest`. Новых внешних зависимостей нет.

**Spec:** `docs/blueprint/specs/2026-09-05-e6-knowledge-base-design.md` (исполнитель читает и спек, и этот план).

## Global Constraints

Скопировано из спека и Ядра. Требования каждой задачи неявно включают этот список.

- **База производна от `runs/`.** `runs/<id>/` — источник истины и иммутабелен; база лишь индексирует его. Каждая запись ссылается на `campaign_run_id`. Переналивка (`rebuild_from_runs`) идемпотентна.
- **Только детерминированные факты** — payload, роли, verdict, severity/chain_stage, evidence-ссылки, время. НЕ проза отчёта.
- **Без внешних зависимостей.** Только `sqlite3` из stdlib.
- **`knowledge.db` вне `runs/`** и вне git — добавить в `.gitignore`.
- **Совместимость с E4.** `payloads_for(profile) -> list[str]` подаётся в `generation.dedup.is_duplicate(candidate, prior)`. `context_for(profile) -> dict` даёт ровно `{"confirmed": [...], "ineffective": [...], "prior_payloads": [...]}` — те же ключи, что читает `generation.generator.generate(..., prior_context=…)` (`prior_context["prior_payloads"]`, `prior_context["ineffective"]`).
- **Источник payload'а — `transcript.jsonl`, НЕ `knowledge.jsonl`.** Спек §1 ссылается на `knowledge.jsonl`, но big-bang его удалил; актуальный per-attempt артефакт — `transcript.jsonl`. Это осознанное расхождение со спеком, зафиксировать в комментарии ingest.
- **Язык:** доки/интерфейс — русский; код/идентификаторы — английский.
- **Проверка:** `.venv/bin/python -m unittest discover -s tests`; на границе каждой задачи набор зелёный (кроме пре-существующего `stand.observability`).
- **Коммиты:** `feat(scope): …`, wrap 72, **без** `Claude-Session`-трейлера.

## Реальные формы артефактов прогона (проверено в коде)

Исполнитель опирается на эти поля дословно — они подтверждены чтением `campaign/orchestrator.py`/`storage/runs.py`:

- `campaign.json`: `{run_id, profile: "name@version", modes: [...], trials, scenarios: [{id, attack_class, standard_refs, actor, payloads, goal, boundary, reset_policy, steps}]}`.
- `transcript.jsonl` (строка на попытку): `{scenario_id, attempt, mode, actor, payload, verdict, outcomes: [{passed, grade, detail}], error, evidence_refs: [...], steps: [...]}`.
- `findings.json`: `{run_id, profile, ..., findings: [{scenario_id, attack_class, standard_refs, verdict, severity, compromise_point, chain_stage, roles, mode, reset_policy, evidence_refs, ...}], ...}` — находка на сценарий (лучшая попытка).
- `observability.json` (может отсутствовать): `{trace_id, trace_url, root_observation_id, warning}`.
- `RunStorage(root)`: `.load_json(run_dir, name)` (для JSON-артефактов), `.list_runs() -> [{run_id, status, run_dir, ...}]`. `transcript.jsonl` — JSONL, читается построчно (не через `load_json`).
- `generation.dedup.tokens(text) -> set[str]`.

## File Structure

```
agentic_redteam/knowledge/
  __init__.py
  store.py     # KnowledgeStore: sqlite-схема, record, payloads_for, record_run, rebuild_from_runs
  ingest.py    # attacks_from_run(run_dir) -> list[dict]  (чистая, из артефактов)
  query.py     # context_for(store, profile_name) -> dict  (сводка для генератора)
tests/
  test_kb_store.py test_kb_ingest.py test_kb_rebuild.py test_kb_query.py
  test_cli_kb.py test_cli_generate_kb.py
```
`.gitignore`: добавить строку `knowledge.db`.

---

### Task 1: Хранилище — схема, record, payloads_for (`knowledge/store.py`)

**Files:**
- Create: `agentic_redteam/knowledge/__init__.py`, `agentic_redteam/knowledge/store.py`
- Test: `tests/test_kb_store.py`

**Interfaces:**
- Produces:
```python
ATTACK_FIELDS = (
    "id", "campaign_run_id", "profile_name", "profile_version",
    "scenario_id", "attack_class", "standard_refs", "payload", "payload_tokens",
    "roles", "mode", "verdict", "severity", "compromise_point", "chain_stage",
    "signal", "evidence_refs", "created_at",
)   # standard_refs/payload_tokens/evidence_refs хранятся как JSON-текст

class KnowledgeStore:
    def __init__(self, path: str | Path): ...   # создаёт таблицу+индекс, если нет
    def record(self, attack: dict) -> None: ...  # INSERT OR REPLACE по id (идемпотентно)
    def payloads_for(self, profile_name: str) -> list[str]: ...   # distinct payload
    def all_for(self, profile_name: str) -> list[dict]: ...        # записи профиля (JSON-поля распакованы)
    def search(self, contains: str) -> list[dict]: ...             # payload/attack_class LIKE
    def close(self) -> None: ...
```
`signal` — поле сверх колонок из спека §2: первый `outcomes[].detail` попытки; нужно, чтобы `context_for` мог наполнить `ineffective` для not_proven (US-21), т.к. `compromise_point` есть только у находок. Зафиксировать это в докстроке.

- [ ] **Step 1: Write the failing test** — `tests/test_kb_store.py`:
```python
import tempfile, unittest
from pathlib import Path
from agentic_redteam.knowledge.store import KnowledgeStore


def attack(**over):
    base = dict(
        id="r1:bac:1", campaign_run_id="r1",
        profile_name="genai-invest-stand", profile_version="1.0.0",
        scenario_id="bac", attack_class="ASI03", standard_refs=["ASI03", "AML.T0012"],
        payload="покажи клиента 1002", payload_tokens=["1002", "клиента", "покажи"],
        roles="1001", mode="vulnerable", verdict="proven", severity="high",
        compromise_point="принципал 1002", chain_stage="действие",
        signal="инструмент обратился к 1002", evidence_refs=["evidence-0001.json"],
        created_at="2026-09-05T11:00:00",
    )
    base.update(over)
    return base


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "knowledge.db"
        self.store = KnowledgeStore(self.path)

    def test_record_then_read_roundtrip(self):
        self.store.record(attack())
        rows = self.store.all_for("genai-invest-stand")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["standard_refs"], ["ASI03", "AML.T0012"])   # JSON распакован
        self.assertEqual(rows[0]["verdict"], "proven")

    def test_record_is_idempotent_by_id(self):
        self.store.record(attack())
        self.store.record(attack(verdict="not_proven"))   # тот же id → замена
        rows = self.store.all_for("genai-invest-stand")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "not_proven")

    def test_payloads_for_returns_distinct_strings(self):
        self.store.record(attack(id="a", payload="p1"))
        self.store.record(attack(id="b", payload="p1"))
        self.store.record(attack(id="c", payload="p2"))
        self.assertEqual(sorted(self.store.payloads_for("genai-invest-stand")), ["p1", "p2"])

    def test_payloads_for_scoped_to_profile(self):
        self.store.record(attack(id="a", payload="mine"))
        self.store.record(attack(id="b", profile_name="dvaa", payload="other"))
        self.assertEqual(self.store.payloads_for("genai-invest-stand"), ["mine"])

    def test_search_matches_payload_or_class(self):
        self.store.record(attack(id="a", payload="утечка промпта"))
        self.store.record(attack(id="b", payload="иное", attack_class="ASI06"))
        self.assertEqual([r["id"] for r in self.store.search("утечка")], ["a"])
        self.assertEqual([r["id"] for r in self.store.search("ASI06")], ["b"])

    def test_reopen_persists(self):
        self.store.record(attack())
        self.store.close()
        again = KnowledgeStore(self.path)
        self.assertEqual(len(again.all_for("genai-invest-stand")), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_kb_store -v`
Expected: FAIL — `ModuleNotFoundError: agentic_redteam.knowledge.store`

- [ ] **Step 3: Write minimal implementation** — `agentic_redteam/knowledge/__init__.py` пустой; `agentic_redteam/knowledge/store.py`:
```python
"""База знаний о проведённых атаках: sqlite, производна от runs/."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ATTACK_FIELDS = (
    "id", "campaign_run_id", "profile_name", "profile_version",
    "scenario_id", "attack_class", "standard_refs", "payload", "payload_tokens",
    "roles", "mode", "verdict", "severity", "compromise_point", "chain_stage",
    "signal", "evidence_refs", "created_at",
)
_JSON_FIELDS = ("standard_refs", "payload_tokens", "evidence_refs")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attacks (
  id TEXT PRIMARY KEY, campaign_run_id TEXT,
  profile_name TEXT, profile_version TEXT,
  scenario_id TEXT, attack_class TEXT, standard_refs TEXT,
  payload TEXT, payload_tokens TEXT,
  roles TEXT, mode TEXT,
  verdict TEXT, severity TEXT, compromise_point TEXT, chain_stage TEXT,
  signal TEXT, evidence_refs TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_profile ON attacks(profile_name, profile_version);
"""


class KnowledgeStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, attack: dict) -> None:
        row = {field: attack.get(field) for field in ATTACK_FIELDS}
        for field in _JSON_FIELDS:
            row[field] = json.dumps(row.get(field) or [], ensure_ascii=False)
        placeholders = ", ".join("?" for _ in ATTACK_FIELDS)
        self._conn.execute(
            f"INSERT OR REPLACE INTO attacks ({', '.join(ATTACK_FIELDS)}) VALUES ({placeholders})",
            [row[field] for field in ATTACK_FIELDS],
        )
        self._conn.commit()

    def _rows(self, where: str, params: tuple) -> list[dict]:
        cursor = self._conn.execute(f"SELECT * FROM attacks WHERE {where}", params)
        result = []
        for raw in cursor.fetchall():
            item = dict(raw)
            for field in _JSON_FIELDS:
                item[field] = json.loads(item[field]) if item[field] else []
            result.append(item)
        return result

    def all_for(self, profile_name: str) -> list[dict]:
        return self._rows("profile_name = ?", (profile_name,))

    def payloads_for(self, profile_name: str) -> list[str]:
        cursor = self._conn.execute(
            "SELECT DISTINCT payload FROM attacks WHERE profile_name = ? AND payload IS NOT NULL",
            (profile_name,))
        return [row[0] for row in cursor.fetchall()]

    def search(self, contains: str) -> list[dict]:
        like = f"%{contains}%"
        return self._rows("payload LIKE ? OR attack_class LIKE ?", (like, like))

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_kb_store -v`
Expected: PASS (6 тестов)

- [ ] **Step 5: Commit**

```bash
git add agentic_redteam/knowledge/__init__.py agentic_redteam/knowledge/store.py tests/test_kb_store.py
git commit -m "feat(knowledge): sqlite-хранилище атак с record/payloads_for/search"
```

---

### Task 2: Прогон → записи-атаки (`knowledge/ingest.py`)

**Files:**
- Create: `agentic_redteam/knowledge/ingest.py`
- Test: `tests/test_kb_ingest.py`

**Interfaces:**
- Consumes: `generation.dedup.tokens`; `storage.runs.RunStorage` (для `load_json`) или прямое чтение файлов.
- Produces:
```python
def attacks_from_run(run_dir: str | Path) -> list[dict]: ...
```
Одна запись на строку `transcript.jsonl`. `profile` из `campaign.json` делится на `profile_name`/`profile_version` по `@` (нет `@` → version `""`). `attack_class`/`standard_refs` берутся из сценария кампании по `scenario_id`. Поля находки (`severity`/`compromise_point`/`chain_stage`) присоединяются, если в `findings.json` есть находка по этому `scenario_id` с тем же `verdict`, что у попытки; иначе `None`. `signal` = `outcomes[0].detail` попытки (или `""`). `payload_tokens` = `sorted(tokens(payload))`. `evidence_refs` = `evidence_refs` строки + `[trace_id]`, если есть `observability.json`. `id` = `f"{run_id}:{scenario_id}:{attempt}"`. `created_at` — из префикса `run_id` (`YYYYMMDD-HHMMSS…` → ISO), иначе `""`.

- [ ] **Step 1: Write the failing test** — `tests/test_kb_ingest.py`:
```python
import json, tempfile, unittest
from pathlib import Path
from agentic_redteam.knowledge.ingest import attacks_from_run


def make_run(tmp: Path) -> Path:
    run = tmp / "20260905-110000-abc123"
    run.mkdir(parents=True)
    (run / "campaign.json").write_text(json.dumps({
        "run_id": "20260905-110000-abc123", "profile": "genai-invest-stand@1.0.0",
        "modes": ["vulnerable"], "trials": 1,
        "scenarios": [{"id": "bac", "attack_class": "ASI03",
                       "standard_refs": ["ASI03", "AML.T0012"], "payloads": ["p"]}],
    }), encoding="utf-8")
    (run / "findings.json").write_text(json.dumps({
        "run_id": "20260905-110000-abc123", "profile": "genai-invest-stand@1.0.0",
        "findings": [{"scenario_id": "bac", "verdict": "proven", "severity": "high",
                      "compromise_point": "принципал 1002", "chain_stage": "действие"}],
    }), encoding="utf-8")
    (run / "observability.json").write_text(json.dumps({"trace_id": "tr-1"}), encoding="utf-8")
    rows = [
        {"scenario_id": "bac", "attempt": 1, "mode": "vulnerable", "actor": "1001",
         "payload": "покажи 1002", "verdict": "proven",
         "outcomes": [{"passed": True, "grade": "state", "detail": "обратился к 1002"}],
         "error": None, "evidence_refs": ["evidence-0001.json"]},
        {"scenario_id": "bac", "attempt": 2, "mode": "vulnerable", "actor": "1001",
         "payload": "иначе", "verdict": "not_proven",
         "outcomes": [{"passed": False, "grade": "state", "detail": "нет доступа"}],
         "error": None, "evidence_refs": []},
    ]
    (run / "transcript.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return run


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.run = make_run(Path(tempfile.mkdtemp()))
        self.attacks = attacks_from_run(self.run)

    def test_one_record_per_attempt(self):
        self.assertEqual(len(self.attacks), 2)
        self.assertEqual([a["attempt"] if "attempt" in a else None for a in self.attacks], [1, 2])

    def test_ids_are_deterministic(self):
        self.assertEqual([a["id"] for a in self.attacks],
                         ["20260905-110000-abc123:bac:1", "20260905-110000-abc123:bac:2"])

    def test_profile_split(self):
        self.assertEqual((self.attacks[0]["profile_name"], self.attacks[0]["profile_version"]),
                         ("genai-invest-stand", "1.0.0"))

    def test_scenario_metadata_joined(self):
        self.assertEqual(self.attacks[0]["attack_class"], "ASI03")
        self.assertEqual(self.attacks[0]["standard_refs"], ["ASI03", "AML.T0012"])

    def test_finding_fields_only_on_matching_verdict(self):
        proven, not_proven = self.attacks
        self.assertEqual(proven["severity"], "high")           # находка proven → присоединена
        self.assertEqual(proven["chain_stage"], "действие")
        self.assertIsNone(not_proven["severity"])              # not_proven → нет находки
        self.assertEqual(not_proven["signal"], "нет доступа")  # signal — из outcomes

    def test_tokens_and_trace_ref(self):
        self.assertIn("1002", self.attacks[0]["payload_tokens"])
        self.assertIn("tr-1", self.attacks[0]["evidence_refs"])      # trace-id добавлен
        self.assertIn("evidence-0001.json", self.attacks[0]["evidence_refs"])

    def test_created_at_from_run_id(self):
        self.assertEqual(self.attacks[0]["created_at"], "2026-09-05T11:00:00")

    def test_missing_observability_is_tolerated(self):
        (self.run / "observability.json").unlink()
        again = attacks_from_run(self.run)
        self.assertEqual(again[0]["evidence_refs"], ["evidence-0001.json"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_kb_ingest -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation** — `agentic_redteam/knowledge/ingest.py`:
```python
"""Каталог прогона → записи-атаки. Источник payload'а — transcript.jsonl.

Спек §1 упоминает knowledge.jsonl, но big-bang его удалил; актуальный
per-attempt артефакт — transcript.jsonl. База лишь индексирует runs/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..generation.dedup import tokens

_RUN_TS = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _created_at(run_id: str) -> str:
    match = _RUN_TS.match(run_id or "")
    if not match:
        return ""
    y, mo, d, h, mi, s = match.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}"


def attacks_from_run(run_dir: str | Path) -> list[dict]:
    run = Path(run_dir)
    campaign = _read_json(run / "campaign.json")
    run_id = campaign.get("run_id", run.name)
    name, _, version = str(campaign.get("profile", "")).partition("@")
    scenarios = {s["id"]: s for s in campaign.get("scenarios", []) if isinstance(s, dict)}
    findings = {}
    findings_path = run / "findings.json"
    if findings_path.is_file():
        for finding in _read_json(findings_path).get("findings", []):
            findings.setdefault(finding.get("scenario_id"), []).append(finding)
    trace_refs = []
    obs_path = run / "observability.json"
    if obs_path.is_file():
        trace_id = _read_json(obs_path).get("trace_id")
        if trace_id:
            trace_refs = [trace_id]
    created_at = _created_at(run_id)
    attacks = []
    transcript = run / "transcript.jsonl"
    for line in (transcript.read_text(encoding="utf-8").splitlines() if transcript.is_file() else []):
        if not line.strip():
            continue
        row = json.loads(line)
        scenario_id = row.get("scenario_id")
        scen = scenarios.get(scenario_id, {})
        finding = next((f for f in findings.get(scenario_id, [])
                        if f.get("verdict") == row.get("verdict")), None)
        outcomes = row.get("outcomes") or []
        attacks.append({
            "id": f"{run_id}:{scenario_id}:{row.get('attempt')}",
            "campaign_run_id": run_id,
            "profile_name": name, "profile_version": version,
            "scenario_id": scenario_id,
            "attack_class": scen.get("attack_class"),
            "standard_refs": scen.get("standard_refs", []),
            "payload": row.get("payload"),
            "payload_tokens": sorted(tokens(row.get("payload") or "")),
            "roles": row.get("actor"), "mode": row.get("mode"),
            "verdict": row.get("verdict"),
            "severity": finding.get("severity") if finding else None,
            "compromise_point": finding.get("compromise_point") if finding else None,
            "chain_stage": finding.get("chain_stage") if finding else None,
            "signal": (outcomes[0].get("detail") if outcomes else "") or "",
            "evidence_refs": list(row.get("evidence_refs") or []) + trace_refs,
            "created_at": created_at,
        })
    return attacks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_kb_ingest -v`
Expected: PASS (8 тестов)

- [ ] **Step 5: Commit**

```bash
git add agentic_redteam/knowledge/ingest.py tests/test_kb_ingest.py
git commit -m "feat(knowledge): маппинг артефактов прогона в записи-атаки"
```

---

### Task 3: Наполнение и реиндексация (`knowledge/store.py`)

**Files:**
- Modify: `agentic_redteam/knowledge/store.py`
- Test: `tests/test_kb_rebuild.py`

**Interfaces:**
- Consumes: `attacks_from_run` (Task 2).
- Produces (методы `KnowledgeStore`):
```python
def record_run(self, run_dir: str | Path) -> int: ...           # ingest+record одного прогона, вернуть число записей
def rebuild_from_runs(self, runs_root: str | Path) -> int: ...  # перечитать все runs/*/, вернуть число записей
```
`rebuild_from_runs` идемпотентен (id детерминирован, `INSERT OR REPLACE`): повтор не плодит дублей. Прогоны без `campaign.json` пропускаются (незавершённые/битые).

- [ ] **Step 1: Write the failing test** — `tests/test_kb_rebuild.py`:
```python
import json, tempfile, unittest
from pathlib import Path
from agentic_redteam.knowledge.store import KnowledgeStore
from tests.test_kb_ingest import make_run   # переиспользуем фикстуру прогона


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.runs = Path(tempfile.mkdtemp())
        make_run(self.runs)                      # один валидный прогон (2 попытки)
        (self.runs / "broken").mkdir()           # каталог без campaign.json
        self.store = KnowledgeStore(Path(tempfile.mkdtemp()) / "knowledge.db")

    def test_record_run_counts_attempts(self):
        run = next(p for p in self.runs.iterdir() if (p / "campaign.json").is_file())
        self.assertEqual(self.store.record_run(run), 2)

    def test_rebuild_indexes_all_valid_runs(self):
        self.assertEqual(self.store.rebuild_from_runs(self.runs), 2)   # broken/ пропущен
        self.assertEqual(len(self.store.all_for("genai-invest-stand")), 2)

    def test_rebuild_is_idempotent(self):
        self.store.rebuild_from_runs(self.runs)
        self.store.rebuild_from_runs(self.runs)                        # повтор
        self.assertEqual(len(self.store.all_for("genai-invest-stand")), 2)  # без дублей
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_kb_rebuild -v`
Expected: FAIL — `AttributeError: 'KnowledgeStore' object has no attribute 'record_run'`

- [ ] **Step 3: Write minimal implementation** — в `agentic_redteam/knowledge/store.py` добавить импорт и методы:
```python
# в начало файла, к прочим импортам:
from .ingest import attacks_from_run
```
```python
# методы класса KnowledgeStore:
    def record_run(self, run_dir) -> int:
        attacks = attacks_from_run(run_dir)
        for attack in attacks:
            self.record(attack)
        return len(attacks)

    def rebuild_from_runs(self, runs_root) -> int:
        total = 0
        for run_dir in sorted(Path(runs_root).iterdir()):
            if run_dir.is_dir() and (run_dir / "campaign.json").is_file():
                total += self.record_run(run_dir)
        return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_kb_rebuild -v`
Expected: PASS (3 теста)

- [ ] **Step 5: Commit**

```bash
git add agentic_redteam/knowledge/store.py tests/test_kb_rebuild.py
git commit -m "feat(knowledge): наполнение и идемпотентная реиндексация из runs/"
```

---

### Task 4: Контекст для генератора (`knowledge/query.py`)

**Files:**
- Create: `agentic_redteam/knowledge/query.py`
- Test: `tests/test_kb_query.py`

**Interfaces:**
- Consumes: `KnowledgeStore.all_for` (Task 1).
- Produces:
```python
def context_for(store, profile_name: str) -> dict: ...
# → {"confirmed": [attack_class...], "ineffective": [signal...], "prior_payloads": [payload...]}
```
Ключи и семантика — как у `generation.context.campaign_context`, чтобы результат подавался прямо в `generation.generator.generate(..., prior_context=…)`. `confirmed` = distinct `attack_class` где `verdict == "proven"`; `ineffective` = distinct `signal` где `verdict == "not_proven"` и `signal` непустой; `prior_payloads` = distinct `payload` (в порядке первого появления, детерминированно).

- [ ] **Step 1: Write the failing test** — `tests/test_kb_query.py`:
```python
import tempfile, unittest
from pathlib import Path
from agentic_redteam.knowledge.store import KnowledgeStore
from agentic_redteam.knowledge.query import context_for
from tests.test_kb_store import attack


class ContextForTests(unittest.TestCase):
    def setUp(self):
        self.store = KnowledgeStore(Path(tempfile.mkdtemp()) / "knowledge.db")
        self.store.record(attack(id="a", payload="p1", verdict="proven", attack_class="ASI03"))
        self.store.record(attack(id="b", payload="p2", verdict="not_proven",
                                 attack_class="ASI06", signal="нет доступа", severity=None))
        self.store.record(attack(id="c", payload="p1", verdict="not_proven",
                                 signal="нет доступа", severity=None))   # дубль payload и signal

    def test_shape_matches_generator_prior_context(self):
        ctx = context_for(self.store, "genai-invest-stand")
        self.assertEqual(set(ctx), {"confirmed", "ineffective", "prior_payloads"})

    def test_confirmed_from_proven(self):
        self.assertEqual(context_for(self.store, "genai-invest-stand")["confirmed"], ["ASI03"])

    def test_ineffective_from_not_proven_signals_deduped(self):
        self.assertEqual(context_for(self.store, "genai-invest-stand")["ineffective"], ["нет доступа"])

    def test_prior_payloads_deduped(self):
        self.assertEqual(sorted(context_for(self.store, "genai-invest-stand")["prior_payloads"]),
                         ["p1", "p2"])

    def test_other_profile_empty(self):
        self.assertEqual(context_for(self.store, "dvaa"),
                         {"confirmed": [], "ineffective": [], "prior_payloads": []})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_kb_query -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation** — `agentic_redteam/knowledge/query.py`:
```python
"""Выборки базы знаний для генератора. Форма — как у generation.context."""
from __future__ import annotations


def _distinct(values):
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def context_for(store, profile_name: str) -> dict:
    rows = store.all_for(profile_name)
    return {
        "confirmed": _distinct(r["attack_class"] for r in rows if r["verdict"] == "proven"),
        "ineffective": _distinct(r["signal"] for r in rows if r["verdict"] == "not_proven"),
        "prior_payloads": _distinct(r["payload"] for r in rows),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_kb_query -v`
Expected: PASS (5 тестов)

- [ ] **Step 5: Commit**

```bash
git add agentic_redteam/knowledge/query.py tests/test_kb_query.py
git commit -m "feat(knowledge): context_for в форме prior_context генератора"
```

---

### Task 5: CLI `kb list/search/rebuild` (`app_cli.py`)

**Files:**
- Modify: `agentic_redteam/app_cli.py`, `.gitignore`
- Test: `tests/test_cli_kb.py`

**Interfaces:**
- Consumes: `KnowledgeStore` (Tasks 1/3). Использует существующие в `app_cli`: `PROFILES_ROOT`/`DEFAULT_RUNS_ROOT` (константы каталогов), `PipelineConfigurationError`.
- Produces: подкоманда `kb` с `list` (по профилю), `search --contains X`, `rebuild`. Путь базы — `KB_PATH = <repo>/knowledge.db` (константа в `app_cli`; в `.gitignore`). `--json` поддержан.

- [ ] **Step 1: Write the failing test** — `tests/test_cli_kb.py`:
```python
import contextlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from agentic_redteam.app_cli import main
from agentic_redteam.knowledge.store import KnowledgeStore
from tests.test_kb_store import attack


def run_cli(kb_path, *argv):
    out = io.StringIO()
    with patch("agentic_redteam.app_cli.KB_PATH", kb_path), contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class CliKbTests(unittest.TestCase):
    def setUp(self):
        self.kb = Path(tempfile.mkdtemp()) / "knowledge.db"
        store = KnowledgeStore(self.kb)
        store.record(attack(id="a", payload="утечка промпта", attack_class="LLM08"))
        store.close()

    def test_list_by_profile_json(self):
        code, out = run_cli(self.kb, "kb", "list", "--profile", "genai-invest-stand", "--json")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(len(payload["attacks"]), 1)
        self.assertEqual(payload["attacks"][0]["attack_class"], "LLM08")

    def test_search_contains(self):
        code, out = run_cli(self.kb, "kb", "search", "--contains", "утечка", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(json.loads(out)["attacks"]), 1)

    def test_rebuild_reports_count(self):
        with tempfile.TemporaryDirectory() as runs:
            from tests.test_kb_ingest import make_run
            make_run(Path(runs))
            fresh = Path(tempfile.mkdtemp()) / "kb.db"
            code, out = run_cli(fresh, "kb", "rebuild", "--runs", runs, "--json")
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)["recorded"], 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_cli_kb -v`
Expected: FAIL — argparse не знает `kb` (SystemExit 2) / `KB_PATH` отсутствует

- [ ] **Step 3: Write minimal implementation** — в `agentic_redteam/app_cli.py`:

Импорт и константа пути базы (рядом с `DEFAULT_RUNS_ROOT`):
```python
from .knowledge.store import KnowledgeStore
```
```python
KB_PATH = Path(__file__).resolve().parents[1] / "knowledge.db"
```
Парсер `kb` (рядом с регистрацией других подкоманд в `build_parser`):
```python
    kb = commands.add_parser("kb", help="база знаний о проведённых атаках")
    kb_commands = kb.add_subparsers(dest="kb_command", required=True)
    kb_list = kb_commands.add_parser("list", help="атаки по профилю")
    kb_list.add_argument("--profile", required=True, help="имя профиля (без версии)")
    kb_list.add_argument("--json", action="store_true")
    kb_search = kb_commands.add_parser("search", help="поиск по payload/классу")
    kb_search.add_argument("--contains", required=True)
    kb_search.add_argument("--json", action="store_true")
    kb_rebuild = kb_commands.add_parser("rebuild", help="переналить базу из runs/")
    kb_rebuild.add_argument("--runs", default=str(DEFAULT_RUNS_ROOT), help="корень runs/")
    kb_rebuild.add_argument("--json", action="store_true")
```
Диспетч (рядом с прочими `if args.command == …`):
```python
        if args.command == "kb":
            return _kb(args)
```
Реализация (рядом с `_profile`):
```python
def _kb(args) -> int:
    store = KnowledgeStore(KB_PATH)
    try:
        if args.kb_command == "rebuild":
            count = store.rebuild_from_runs(args.runs)
            if args.json:
                print(json.dumps({"ok": True, "recorded": count}, ensure_ascii=False))
            else:
                print(f"переиндексировано атак: {count}")
            return 0
        if args.kb_command == "list":
            attacks = store.all_for(args.profile)
        else:
            attacks = store.search(args.contains)
        if args.json:
            print(json.dumps({"ok": True, "attacks": attacks}, ensure_ascii=False))
        else:
            for a in attacks:
                print(f"{a['created_at']} · {a['scenario_id']} · {a['attack_class']} · "
                      f"{a['verdict']} · {a['payload']}")
        return 0
    finally:
        store.close()
```
В `.gitignore` добавить строку `knowledge.db`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_cli_kb -v`
Expected: PASS (3 теста)

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3` (только пре-существующий `stand.observability`)
```bash
git add agentic_redteam/app_cli.py .gitignore tests/test_cli_kb.py
git commit -m "feat(cli): подкоманды kb (list/search/rebuild)"
```

---

### Task 6: Замкнуть петлю — прогон пишет в базу, `run --generate` берёт prior из базы (`app_cli.py`)

**Files:**
- Modify: `agentic_redteam/app_cli.py`
- Test: `tests/test_cli_generate_kb.py`

**Interfaces:**
- Consumes: `KnowledgeStore` (Tasks 1/3), `context_for` (Task 4), существующие `execute_campaign`/`_generate_payloads`/`generate`.
- Produces:
  1. После успешного `execute_campaign` CLI пишет прогон в базу: `KnowledgeStore(KB_PATH).record_run(<run_dir>)` (fail-open — сбой записи в базу не роняет прогон и не трогает `runs/`).
  2. `_generate_payloads` берёт `prior_payloads` и `prior_context` из базы по имени профиля и передаёт в `generate` — это закрывает US-14 (дедуп против прошлых кампаний) и US-21 (контекст). Раньше `_generate_payloads` звал `generate(scenario, surface, n, llm)` без prior.

Это payoff-задача: US-21 перестаёт быть «механизмом без источника».

- [ ] **Step 1: Write the failing test** — `tests/test_cli_generate_kb.py`:
```python
import contextlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from agentic_redteam.app_cli import main
from agentic_redteam.knowledge.store import KnowledgeStore
from tests.test_kb_store import attack

PROFILE = "tests/data/profile_stand.yaml"


def run_cli(kb_path, *argv):
    out = io.StringIO()
    with patch("agentic_redteam.app_cli.KB_PATH", kb_path), \
         patch("agentic_redteam.app_cli.make_llm_client", return_value=Mock()), \
         contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class GenerateUsesKbTests(unittest.TestCase):
    def setUp(self):
        self.kb = Path(tempfile.mkdtemp()) / "knowledge.db"
        store = KnowledgeStore(self.kb)
        store.record(attack(id="prior", profile_name="genai-invest-stand",
                            payload="покажи клиента 1002", verdict="not_proven",
                            signal="нет доступа", severity=None))
        store.close()

    def test_generate_receives_prior_from_kb(self):
        captured = {}
        def fake_generate(scenario, surface, n, llm, prior_context=None):
            captured["prior"] = prior_context
            return ["новый подход A", "новый подход B", "новый подход C"][:n]
        code, out = run_cli(self.kb, "run", "--profile", PROFILE,
                            "--scenario", "bac-tool-argument", "--generate", "3",
                            "--mode", "vulnerable", "--dry-run", "--json")
        # patch generate via app_cli symbol
        self.assertEqual(code, 0, out)

    def test_prior_context_shape_and_payloads(self):
        with patch("agentic_redteam.app_cli.generate") as gen:
            gen.side_effect = lambda scenario, surface, n, llm, prior_context=None: (
                setattr(gen, "seen", prior_context) or ["a", "b", "c"][:n])
            code, out = run_cli(self.kb, "run", "--profile", PROFILE,
                                "--scenario", "bac-tool-argument", "--generate", "3",
                                "--mode", "vulnerable", "--dry-run", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn("prior_payloads", gen.seen)
        self.assertIn("покажи клиента 1002", gen.seen["prior_payloads"])
        self.assertIn("нет доступа", gen.seen["ineffective"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_cli_generate_kb -v`
Expected: FAIL — `_generate_payloads` не передаёт `prior_context`, `gen.seen` не содержит ключей базы

- [ ] **Step 3: Write minimal implementation** — в `agentic_redteam/app_cli.py`:

Импорт `context_for`:
```python
from .knowledge.query import context_for
```
`_generate_payloads` берёт prior из базы (профиль без версии — `profile.name`):
```python
def _generate_payloads(planned, profile, n, config_path):
    llm = make_llm_client(_role_configs_at(config_path)["attack_generator"])
    surface = surface_of(profile)
    store = KnowledgeStore(KB_PATH)
    try:
        prior_context = context_for(store, profile.name)
    finally:
        store.close()
    updated = []
    for scenario in planned:
        if any(step.payload for step in scenario.steps):
            payloads = generate(scenario, surface, n, llm, prior_context=prior_context)
            scenario = replace(scenario, payloads=payloads)
        updated.append(scenario)
    return updated
```
Запись прогона в базу после исполнения — в `_execute_campaign`, после `execute_campaign(...)` вернул `summary` (fail-open):
```python
    try:
        store = KnowledgeStore(KB_PATH)
        try:
            store.record_run(summary["run_dir"])
        finally:
            store.close()
    except Exception:
        pass   # наблюдательная запись в базу не влияет на прогон и runs/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_cli_generate_kb -v`
Expected: PASS

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -5` — все CLI-тесты (`test_cli*`) зелёные, только пре-существующий `stand.observability` падает.
```bash
git add agentic_redteam/app_cli.py tests/test_cli_generate_kb.py
git commit -m "feat(cli): дедуп и контекст из базы знаний в run --generate (US-14/US-21)"
```

---

## Self-Review

**Spec coverage:**
- §1 поля записи → Task 1 (`ATTACK_FIELDS`) + Task 2 (маппинг из артефактов). Расхождение `knowledge.jsonl`→`transcript.jsonl` зафиксировано в Global Constraints и докстроке ingest.
- §2 хранилище (sqlite, схема, индекс) → Task 1.
- §3 наполнение (runner-append, baseline-источник, `kb rebuild`) → Task 3 (`record_run`/`rebuild_from_runs`) + Task 6 (CLI пишет прогон после исполнения). Baseline как источник: `rebuild_from_runs` переиндексирует любые `runs/`, включая прогоны baseline-сценариев.
- §4 питание генерации → Task 4 (`context_for`) + Task 6 (проводка в `run --generate`); `payloads_for` (Task 1) → дедуп.
- §5 область базы (по агенту) → индекс `ix_profile`, выборки по `profile_name`. Расширение до организации/библиотеки интерфейс не блокирует — не реализуем (открытый вопрос владельца).
- §6 CLI (`kb list/search/rebuild`) → Task 5.
- §7 модули/интерфейсы → `store.py`/`query.py` (+ `ingest.py` как чистый маппинг, выделен ради тестируемости). Сигнатуры `record`/`payloads_for`/`context_for`/`rebuild_from_runs` совпадают со спеком.
- §8 трассируемость US-19/US-14/US-21 → Tasks 1–6; US-21 проводка закрыта Task 6.

**Placeholder scan:** каждый шаг несёт реальный код/тест. Нет «TBD»/«add error handling».

**Type consistency:** `ATTACK_FIELDS`/`_JSON_FIELDS` — единый набор в Tasks 1/2/3. `attacks_from_run -> list[dict]` тех же ключей, что пишет `record` (Tasks 2→1/3). `context_for -> {confirmed, ineffective, prior_payloads}` (Task 4) = ключи, что читает `generate(prior_context=…)` (Task 6, сверено с `generation/generator.py`). `KB_PATH`/`KnowledgeStore` — Tasks 5/6. `payloads_for`/`all_for`/`search`/`record_run`/`rebuild_from_runs` — согласованы между store и вызывающими.

**Известное расхождение со спеком (зафиксировано):** источник payload'а — `transcript.jsonl`, не `knowledge.jsonl` (последний удалён big-bang). Плюс поле `signal` добавлено сверх колонок §2 — оно нужно, чтобы `context_for` наполнял `ineffective` для not_proven (US-21), т.к. `compromise_point` есть только у находок.

**Область (§5) не реализуется** сверх «по агенту» — сознательно, это открытый продуктовый вопрос; интерфейс (`profile_name`-фильтр) не блокирует расширение.
