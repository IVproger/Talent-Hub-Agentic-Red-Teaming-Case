"""MOROK web UI — FastAPI поверх движка agentic_redteam.

Отдаёт фронтенд дизайн-кита (webui/static) и API: запуск кампании в фоне,
статус/лог, история, находки, отчёт, список сценариев. Прогон реальный —
`execute_agentic_campaign`, тот же, что у CLI/Streamlit.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

# credential ролей минтится через `docker exec` в стенд; PATH процесса (напр.
# запущенного из nohup/сервиса) может не содержать путь к docker — добавим его,
# иначе минт падает с «Невозможно разрешить шаблон credential».
for _bin in ("/usr/local/bin", "/opt/homebrew/bin"):
    if _bin not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")

import re

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fpdf import FPDF
from pypdf import PdfReader

from agentic_redteam.app_cli import (
    _agentic_budget, _config_mapping, _role_configs_at, build_baseline,
    execute_agentic_campaign, load_profile, make_llm_client, new_run_id,
)
from agentic_redteam.campaign.agentic import predicate_scenarios
from agentic_redteam.profile.ingest import build_draft, read_document
from agentic_redteam.reporting.business import build_business_report
from agentic_redteam.profile.schema import TargetProfile
from agentic_redteam.storage.runs import RunStorage

REPO = Path(__file__).resolve().parents[1]
RUNS_ROOT = REPO / "runs"
CONFIG = str(REPO / "config" / "target.yaml")
STATIC = Path(__file__).resolve().parent / "static"
PROFILE_REF = "genai-invest-stand@1.0.0"  # fallback-профиль (демо без загрузки)
STAND_URL = "http://localhost:8600"

app = FastAPI(title="MOROK")
_CANCEL: dict[str, threading.Event] = {}
# Цель, собранная из загруженных артефактов (процесс-локально).
_TARGET: dict = {"dir": None, "files": [], "openapi": None, "profile_path": None}


def _find_openapi(paths):
    for path in paths:
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("paths"), dict):
            return str(path)
    return None


def _build_profile_from_target() -> str:
    op = _TARGET["openapi"]
    docs = [p for p in _TARGET["files"] if p != op]
    roles = _role_configs_at(CONFIG)
    analyst = make_llm_client(roles["analyst"])
    judge = make_llm_client(roles["judge"])
    # Механизм аутентификации/минтинга — знание оператора, не выводимое из
    # артефактов: берём его из верифицированного профиля стенда (провайдер,
    # config, credential, principal), роли/entrypoint/surface выводит LLM.
    op_ident = load_profile(PROFILE_REF).identities
    operator_identities = {k: op_ident[k] for k in
                           ("provider", "config", "credential", "principal")
                           if k in op_ident}
    draft = build_draft(op, STAND_URL, "target-" + Path(op).stem,
                        documents=docs, analyst=analyst, judge=judge,
                        identities=operator_identities)
    TargetProfile.from_mapping(draft)
    out = Path(op).parent / "profile.yaml"
    out.write_text(yaml.safe_dump(draft, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(out)


def _bg(run_id: str, cancel: threading.Event, scenario: str | None = None) -> None:
    storage = RunStorage(RUNS_ROOT)
    log: list[str] = []

    def progress(label: str) -> None:
        log.append(label)
        storage.write_json(storage.root / run_id, "status.json",
                           {"run_id": run_id, "status": "running", "label": label,
                            "log": log[-50:]})

    try:
        config = _config_mapping(CONFIG)
        documents = None
        if _TARGET["openapi"]:
            names = [Path(p).name for p in _TARGET["files"]]
            progress(f"Артефакты: {len(names)} — {', '.join(names)}")
            if not _TARGET["profile_path"]:
                progress("Сборка профиля из артефактов…")
                _TARGET["profile_path"] = _build_profile_from_target()
            profile = load_profile(_TARGET["profile_path"])
            progress(f"Профиль собран: {profile.name}@{profile.version}")
            doc_paths = [p for p in _TARGET["files"] if p != _TARGET["openapi"]]
            documents = [read_document(p) for p in doc_paths]
            if documents:
                progress(f"Документы для генератора: {len(documents)} — "
                         + ", ".join(Path(p).name for p in doc_paths))
        else:
            profile = load_profile(PROFILE_REF)  # демо без загрузки артефактов
            progress(f"Профиль: {profile.name}@{profile.version} (демо-стенд)")
        budget = _agentic_budget(config, None)
        execute_agentic_campaign(profile, config, str(RUNS_ROOT), run_id,
                                 budget=budget, documents=documents,
                                 should_stop=cancel.is_set, on_progress=progress,
                                 only=scenario)
    except Exception as exc:  # noqa: BLE001
        storage.write_json(storage.root / run_id, "status.json",
                           {"run_id": run_id, "status": "failed", "error": str(exc)})


@app.get("/api/target")
def target() -> dict:
    return {"files": [Path(p).name for p in _TARGET["files"]],
            "openapi": Path(_TARGET["openapi"]).name if _TARGET["openapi"] else None}


@app.post("/api/target/upload")
async def target_upload(files: list[UploadFile] = File(...)) -> dict:
    if _TARGET["dir"] is None:
        _TARGET["dir"] = tempfile.mkdtemp(prefix="morok-target-")
    for f in files:
        dest = Path(_TARGET["dir"]) / (f.filename or "file")
        dest.write_bytes(await f.read())
        if str(dest) not in _TARGET["files"]:
            _TARGET["files"].append(str(dest))
    _TARGET["openapi"] = _find_openapi(_TARGET["files"])
    _TARGET["profile_path"] = None  # новые артефакты → пересобрать профиль
    return target()


@app.post("/api/target/reset")
def target_reset() -> dict:
    _TARGET.update({"dir": None, "files": [], "openapi": None, "profile_path": None})
    return target()


@app.post("/api/run")
def start_run(scenario: str | None = None) -> dict:
    # scenario=None или "all" → все предикаты; иначе один сценарий по id
    only = None if (not scenario or scenario == "all") else scenario
    run_id = new_run_id()
    RunStorage(RUNS_ROOT).write_json(RUNS_ROOT / run_id, "status.json",
                                     {"run_id": run_id, "status": "running",
                                      "label": "Подготовка", "log": []})
    cancel = threading.Event()
    _CANCEL[run_id] = cancel
    threading.Thread(target=_bg, args=(run_id, cancel, only), daemon=True).start()
    return {"run_id": run_id}


@app.post("/api/run/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    event = _CANCEL.get(run_id)
    if event is not None:
        event.set()
    return {"ok": True}


@app.get("/api/status/{run_id}")
def status(run_id: str) -> dict:
    try:
        return RunStorage(RUNS_ROOT).load_json(RUNS_ROOT / run_id, "status.json")
    except (OSError, ValueError):
        return {"run_id": run_id, "status": "running", "label": "…", "log": []}


@app.get("/api/runs")
def runs() -> list:
    return RunStorage(RUNS_ROOT).list_runs()


@app.get("/api/runs/{run_id}/findings")
def findings(run_id: str) -> dict:
    try:
        return RunStorage(RUNS_ROOT).load_json(RUNS_ROOT / run_id, "findings.json")
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="findings not found")


@app.get("/api/runs/{run_id}/report", response_class=PlainTextResponse)
def report(run_id: str) -> str:
    path = RUNS_ROOT / run_id / "report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="report not found")
    return path.read_text(encoding="utf-8")


def _read_reg(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
        except Exception:  # noqa: BLE001
            return ""
    try:
        return read_document(str(path)).get("text", "")
    except Exception:  # noqa: BLE001
        return ""


def _business_prompt(findings, business, audiences, note, regs_text) -> str:
    business = business or {}
    proven = [a.get("scenario_id", "") for a in findings.get("attempts", []) if a.get("verdict") == "proven"]
    prohibited = "; ".join(p.get("statement", "") for p in business.get("prohibited_actions") or []) or "не заданы"
    intended = "; ".join(e.get("statement", "") for e in business.get("intended_effects") or []) or "не задана"
    return "\n".join([
        "Ты пишешь ДЕЛОВОЙ документ по итогам авторизованного ред-тиминга ИИ-агента.",
        "Аудитория: " + (", ".join(audiences) or "руководство") + ". Пиши языком риска и решений,",
        "без технического жаргона. НЕ копируй технический отчёт — это отдельный деловой документ.",
        "Строго эти разделы Markdown: «1. Резюме для принятия решения», «2. Что произошло и почему это риск»,",
        "«3. Соответствие требованиям», «4. Варианты решения и стоимость», «5. Критерий закрытия», «6. Приложения».",
        "",
        "Данные прогона (опирайся ТОЛЬКО на них; ничего не выдумывай, финансовый ущерб не оценивай):",
        f"- Профиль: {findings.get('profile')}",
        f"- ASR: {findings.get('asr_percent')}% · доказано {findings.get('scenarios_proven')}/{findings.get('scenarios_scored')} сценариев",
        "- Доказанные находки: " + ("; ".join(proven) or "нет"),
        f"- Заявленные запреты профиля: {prohibited}",
        f"- Заявленная польза продукта: {intended}",
        "",
        "Пожелания заказчика к документу: " + (note.strip() or "—"),
        "",
        "Приложенные регламенты/политики (для раздела «Соответствие требованиям»; ссылайся только на реально приложенное):",
        (regs_text[:6000] or "не приложены"),
        "",
        "Верни только Markdown документа, без пояснений.",
    ])


@app.post("/api/runs/{run_id}/business")
async def business_generate(run_id: str, audience: str = Form(""), note: str = Form(""),
                            files: list[UploadFile] = File(default=[])) -> dict:
    storage = RunStorage(RUNS_ROOT)
    try:
        findings = storage.load_json(RUNS_ROOT / run_id, "findings.json")
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="findings not found")
    try:
        business = load_profile(findings.get("profile", "")).business
    except Exception:  # noqa: BLE001
        business = {}
    tmp = Path(tempfile.mkdtemp(prefix="morok-reg-"))
    regs = []
    # технический отчёт прогона всегда прикрепляется как артефакт-источник
    report_path = RUNS_ROOT / run_id / "report.md"
    if report_path.exists():
        regs.append("### Технический отчёт (report.md)\n" + report_path.read_text(encoding="utf-8"))
    for f in files or []:
        dest = tmp / (f.filename or "reg")
        dest.write_bytes(await f.read())
        text = _read_reg(dest)
        if text.strip():
            regs.append("### " + (f.filename or "") + "\n" + text.strip())
    audiences = [a.strip() for a in audience.split(",") if a.strip()]

    markdown = None
    try:
        llm = make_llm_client(_role_configs_at(CONFIG)["report_writer"])
        markdown = llm.complete(_business_prompt(findings, business, audiences, note, "\n\n".join(regs)))
    except Exception:  # noqa: BLE001
        markdown = None
    if not markdown or not markdown.strip():
        proven = [{
            "scenario_id": a.get("scenario_id"), "attack_class": a.get("attack_class"),
            "standard_refs": a.get("standard_refs", []), "verdict": "proven",
            "severity": "Критично", "evidence_refs": [],
        } for a in findings.get("attempts", []) if a.get("verdict") == "proven"]
        compat = dict(findings)
        compat["findings"] = proven
        markdown = build_business_report(compat, business, reporter_llm=None)

    (RUNS_ROOT / run_id / "business-report.md").write_text(markdown, encoding="utf-8")
    return {"markdown": markdown, "audiences": audiences, "regs": len(regs)}


@app.get("/api/runs/{run_id}/business", response_class=PlainTextResponse)
def business_download(run_id: str) -> str:
    path = RUNS_ROOT / run_id / "business-report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="business report not generated")
    return path.read_text(encoding="utf-8")


FONTS = REPO / "webui" / "fonts"


def _clean_md(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # ссылки → текст
    text = text.replace("**", "").replace("__", "").replace("`", "").replace("*", "")
    return text.strip()


def _md_to_pdf(text: str) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    width = pdf.epw
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            pdf.ln(2)
            continue
        head = re.match(r"^(#{1,6})\s+(.*)", line)
        if head:
            size = {1: 17, 2: 14, 3: 12}.get(len(head.group(1)), 11)
            pdf.ln(2)
            pdf.set_font("DejaVu", "B", size)
            pdf.multi_cell(width, size * 0.55, _clean_md(head.group(2)))
            pdf.ln(1)
            continue
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):  # строка-разделитель таблицы
                continue
            pdf.set_font("DejaVu", "", 9)
            pdf.multi_cell(width, 4.6, _clean_md("  ·  ".join(cells)))
            continue
        if re.match(r"^\s*[-*]\s+", line):
            pdf.set_font("DejaVu", "", 11)
            pdf.multi_cell(width, 5.2, "•  " + _clean_md(re.sub(r"^\s*[-*]\s+", "", line)))
            continue
        pdf.set_font("DejaVu", "", 11)
        pdf.multi_cell(width, 5.2, _clean_md(line))
    return bytes(pdf.output())


@app.get("/api/runs/{run_id}/business.pdf")
def business_pdf(run_id: str) -> Response:
    path = RUNS_ROOT / run_id / "business-report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="business report not generated")
    data = _md_to_pdf(path.read_text(encoding="utf-8"))
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="business-{run_id}.pdf"'})


@app.get("/api/scenarios")
def scenarios() -> list:
    profile = load_profile(PROFILE_REF)
    planned, _coverage = build_baseline(profile)
    return [{
        "id": s.id,
        "attack_class": s.attack_class,
        "standard_refs": list(s.standard_refs or []),
        "goal": [g.get("type") for g in s.goal],
        "boundary": s.boundary,
    } for s in predicate_scenarios(planned)]


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))
