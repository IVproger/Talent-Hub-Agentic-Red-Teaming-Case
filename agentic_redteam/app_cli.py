"""Unified human-first and script-friendly command line interface."""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import secrets
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import __version__
from .assertions.registry import required_kinds
from .adapters.base import AdapterFeature
from .adapters.http_chat import HttpChatAdapter
from .campaign.orchestrator import PlannedScenario, run_campaign
from .reporting.technical import add_narrative, build_skeleton
from .campaign.plan import Campaign, execution_order
from .campaign.runner import RunnerDeps, ScenarioStep
from .campaign.scenarios import resolve as resolve_specs
from .stand_bootstrap import target_model_from_config
from .doctor import checks_ok, run_checks
from .evidence.bundle import EvidenceBundle
from .evidence.calibrate import check, verify
from .generation.composer import PROVIDER_KINDS
from .generation.generator import generate
from .knowledge.store import STATUSES, KnowledgeStore, UnknownStatus
from .knowledge.query import context_for
from .observability import LangfuseTelemetry, langfuse_config_from_mapping
from .llm import (
    LLMConfigurationError,
    LLMRequestError,
    make_llm_client,
    role_configs_from_mapping,
)
from .errors import PipelineConfigurationError, sanitize_error
from .profile.diff import diff as profile_diff
from .profile.registry import ProfileRegistry
from .profile.schema import TargetProfile
from .stand_sync import StandSyncError, sync_stand
from .storage.runs import RunStorage
from .target_runtime import TargetConfigurationError


DEFAULT_RUNS_ROOT = Path(__file__).resolve().parents[1] / "runs"
KB_PATH = Path(__file__).resolve().parents[1] / "knowledge.db"
VERSION = __version__
EXIT_USAGE = 2
EXIT_PREFLIGHT = 3
EXIT_PROVIDER = 4
EXIT_PIPELINE = 5


class CLIArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that preserves the one-JSON-document CLI contract."""

    json_errors_enabled = False

    def error(self, message: str) -> None:
        if self.json_errors_enabled:
            print(
                json.dumps(
                    {"ok": False, "error": message, "exit_code": EXIT_USAGE},
                    ensure_ascii=False,
                )
            )
            raise SystemExit(EXIT_USAGE)
        super().error(message)


def build_parser() -> argparse.ArgumentParser:
    parser = CLIArgumentParser(
        prog="python -m agentic_redteam",
        description="Проверки безопасности целевого агента на основе состояния (state-based).",
        epilog=(
            "Примеры: python -m agentic_redteam profile coverage --profile name@1.0.0; "
            "python -m agentic_redteam run --profile name@1.0.0 --scenario all --dry-run"
        ),
    )
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="проверить локальное окружение, ничего не меняя")
    _add_config_path(doctor)
    doctor.add_argument("--profile", help="профиль цели: name@version или путь к YAML")
    doctor.add_argument("--offline", action="store_true", help="проверять только файлы и конфигурацию")
    doctor.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    run = commands.add_parser("run", help="прогнать кампанию по профилю цели")
    _add_config_path(run)
    run.add_argument(
        "--profile",
        help="профиль цели: name@version из реестра или путь к YAML",
    )
    run.add_argument(
        "--mode",
        help="режимы кампании через запятую, например vulnerable,protected",
    )
    run.add_argument(
        "--from",
        dest="from_run",
        metavar="RUN_DIR",
        help="повторить кампанию, сохранённую в runs/<id>/campaign.json",
    )
    run.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="id сценария, путь к YAML или all; повторяйте для нескольких",
    )
    run.add_argument("-n", "--trials", type=int, default=1,
                     help="прогонов на payload (по умолчанию: 1)")
    run.add_argument("--generate", type=int, metavar="N",
                     help="сгенерировать N payload-вариантов на сценарий (LLM)")
    run.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_RUNS_ROOT),
        help="корневой каталог для артефактов запусков",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="показать план и payload'ы, ничего не отправляя цели",
    )
    run.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    profile_cmd = commands.add_parser("profile", help="работа с профилями цели")
    profile_commands = profile_cmd.add_subparsers(dest="profile_command", required=True)
    for name, help_text in (
        ("list", "перечислить профили реестра"),
        ("show", "карта поверхности профиля"),
        ("diff", "различия двух версий профиля"),
        ("coverage", "что проверяемо на этой цели (гейт покрытия)"),
        ("check", "read-only проверка подключения и привязок источников"),
        ("verify", "проба видимости памяти — МЕНЯЕТ состояние цели"),
        ("init", "черновик профиля из OpenAPI (структура — да, семантика — гипотезы)"),
    ):
        sub = profile_commands.add_parser(name, help=help_text)
        if name == "init":
            sub.add_argument("--openapi", required=True, help="OpenAPI-документ (JSON или YAML)")
            sub.add_argument("--base-url", required=True, dest="base_url",
                             help="точка входа цели")
            sub.add_argument("--name", help="имя профиля (по умолчанию из info.title)")
            sub.add_argument("--version", default="0.1.0", help="версия профиля (SemVer)")
            sub.add_argument("--offline", action="store_true",
                             help="без LLM: привязки — эвристики по именам, помечены TODO")
            sub.add_argument("-o", "--output", help="куда записать черновик (иначе stdout)")
        if name in ("show", "coverage", "check", "verify"):
            sub.add_argument("--profile", required=True, help="name@version или путь к YAML")
        if name == "coverage":
            sub.add_argument("--scenario", action="append", default=[],
                             help="id сценария или путь; повторяйте, по умолчанию весь каталог")
        if name == "diff":
            sub.add_argument("left", help="name@version или путь к YAML")
            sub.add_argument("right", help="name@version или путь к YAML")
        sub.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    report = commands.add_parser("report", help="пересобрать отчёт из сохранённого запуска")
    report.add_argument("--run", required=True, help="каталог сохранённого прогона")
    _add_config_path(report)
    report.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    stand = commands.add_parser("stand", help="управление настроенным целевым стендом")
    stand_commands = stand.add_subparsers(dest="stand_command", required=True)
    stand_sync = stand_commands.add_parser(
        "sync", help="применить модель bootstrap-профиля в stand/.env"
    )
    _add_config_path(stand_sync)
    stand_sync.add_argument(
        "--dry-run", action="store_true", help="показать управляемые изменения без записи"
    )
    stand_sync.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    kb = commands.add_parser("kb", help="база знаний о проведённых атаках")
    kb_commands = kb.add_subparsers(dest="kb_command", required=True)
    kb_list = kb_commands.add_parser("list", help="атаки по профилю")
    kb_list.add_argument("--profile", required=True, help="имя профиля (без версии)")
    kb_list.add_argument("--json", action="store_true")
    kb_search = kb_commands.add_parser("search", help="поиск по payload/классу")
    kb_search.add_argument("--contains", required=True)
    kb_search.add_argument("--json", action="store_true")
    kb_status = kb_commands.add_parser("status", help="судьба находки: показать или сдвинуть статус")
    kb_status.add_argument("attack_id", help="идентификатор находки (run:scenario:attempt)")
    kb_status.add_argument("--set", dest="new_status", choices=STATUSES,
                           help="новый статус находки")
    kb_status.add_argument("--note", default="", help="комментарий к переходу")
    kb_status.add_argument("--json", action="store_true",
                           help="вывести один JSON-результат в stdout")

    kb_rebuild = kb_commands.add_parser("rebuild", help="переналить базу из runs/")
    kb_rebuild.add_argument("--runs", default=str(DEFAULT_RUNS_ROOT), help="корень runs/")
    kb_rebuild.add_argument("--json", action="store_true")

    serve = commands.add_parser("serve", help="запустить локальный интерфейс Streamlit")
    serve.add_argument(
        "--address",
        choices=("127.0.0.1", "localhost"),
        default="127.0.0.1",
        help="локальный адрес привязки (по умолчанию: 127.0.0.1)",
    )
    serve.add_argument("--port", type=_port, default=8502, help="порт привязки (по умолчанию: 8502)")
    return parser


def _add_config_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "config" / "target.yaml"),
        help="целевая конфигурация YAML",
    )


def _role_configs(args) -> dict:
    return _role_configs_at(args.config)


def _role_configs_at(config_path) -> dict:
    config_path = Path(config_path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineConfigurationError(f"Не удалось прочитать конфигурацию: {config_path}") from exc
    if not isinstance(raw, Mapping):
        raise PipelineConfigurationError("Конфигурация должна быть YAML-отображением (mapping).")
    roles = role_configs_from_mapping(raw.get("llm"))
    return roles


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = sys.argv[1:] if argv is None else argv
    CLIArgumentParser.json_errors_enabled = "--json" in arguments
    try:
        args = parser.parse_args(arguments)
    finally:
        CLIArgumentParser.json_errors_enabled = False
    try:
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "run":
            return _run_scenarios(args)
        if args.command == "profile":
            return _profile(args)
        if args.command == "report":
            return _report(args)
        if args.command == "stand" and args.stand_command == "sync":
            return _stand_sync(args)
        if args.command == "kb":
            return _kb(args)
        if args.command == "serve":
            return _serve(args)
        parser.error("неизвестная команда")
    except (LLMConfigurationError, PipelineConfigurationError, StandSyncError) as exc:
        _error(sanitize_error(exc), getattr(args, "json", False), EXIT_USAGE)
        return EXIT_USAGE
    except TargetConfigurationError as exc:
        _error(sanitize_error(exc), getattr(args, "json", False), EXIT_PREFLIGHT)
        return EXIT_PREFLIGHT
    except LLMRequestError as exc:
        result = getattr(exc, "result", None)
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": sanitize_error(exc),
                        "exit_code": EXIT_PROVIDER,
                        "run": asdict(result) if result else None,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            _error(sanitize_error(exc), False, EXIT_PROVIDER)
            if result:
                print(f"запуск: {result.run_dir}", file=sys.stderr)
        return EXIT_PROVIDER
    except KeyboardInterrupt:
        print("Прервано.", file=sys.stderr)
        return 130
    except Exception as exc:  # keep expected operational failures concise
        _error(sanitize_error(exc), getattr(args, "json", False), EXIT_PIPELINE)
        return EXIT_PIPELINE
    return 0


def _doctor(args) -> int:
    if args.profile:
        return _calibrate(args, check)
    roles = _role_configs(args)
    try:
        raw = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
        target_settings = raw.get("target", {}) or {}
        target_api = target_settings.get("endpoint")
        compose_file = target_settings.get("compose_file")
    except (OSError, yaml.YAMLError, AttributeError) as exc:
        raise PipelineConfigurationError(f"Could not read configuration: {args.config}") from exc
    checks = run_checks(
        roles,
        target_model=target_model_from_config(raw, args.config),
        target_api=str(target_api) if target_api else None,
        compose_file=str(compose_file) if compose_file else None,
        check_network=not args.offline,
    )
    if args.json:
        ok = checks_ok(checks)
        print(
            json.dumps(
                {
                    "ok": ok,
                    "exit_code": 0 if ok else EXIT_PREFLIGHT,
                    "checks": [item.to_dict() for item in checks],
                }
            )
        )
    else:
        for item in checks:
            marker = "ок" if item.ok else "сбой"
            print(f"[{marker}] {item.name}: {item.message}")
    return 0 if checks_ok(checks) else EXIT_PREFLIGHT


def _run_scenarios(args) -> int:
    if args.trials < 1:
        raise PipelineConfigurationError("--trials должен быть не меньше 1.")
    if args.generate is not None and args.generate < 1:
        raise PipelineConfigurationError("--generate должен быть не меньше 1.")
    if not args.profile and not args.from_run:
        raise PipelineConfigurationError(
            "Укажите --profile name@version|path.yaml (или --from runs/<id> для повтора)."
        )
    if args.dry_run:
        return _preview_campaign(args)
    return _execute_campaign(args)


def _preview_campaign(args) -> int:
    """US-16: собрать кампанию из профиля и показать план с payload'ами.

    Предпросмотр не трогает цель, поэтому адаптер здесь не нужен: профиль даёт
    состав и принципалы ролей, каталог — цепочки шагов и payload'ы.
    """
    _reject_conflicting_sources(args)
    if args.from_run:
        campaign, planned, scope = _campaign_from_run(args.from_run)
    else:
        campaign, planned, scope = _campaign_from_profile(args)
    payload = {
        "ok": True,
        "dry_run": True,
        "campaign": asdict(campaign),
        "modes_scope": scope,
        "execution_order": [
            {"mode": mode, "scenario": scenario}
            for mode, scenario in execution_order(campaign, scope)
        ],
        "scenarios": [preview_scenario(item) for item in planned],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(_render_preview(payload))
    return 0


PROFILES_ROOT = Path(__file__).resolve().parents[1] / "profiles"


def _reject_conflicting_sources(args) -> None:
    if args.profile and args.from_run:
        raise PipelineConfigurationError(
            "--from повторяет сохранённую кампанию целиком; --profile с ним не сочетается."
        )


def new_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def execute_campaign(profile, planned, modes, trials, output_root, run_id,
                     reporter_llm=None, on_event=None, telemetry=None) -> dict:
    """Собрать реальные адаптер и evidence по профилю и прогнать кампанию.

    Общее ядро запуска: CLI и UI зовут его, а не повторяют сборку зависимостей —
    иначе демо и рабочий инструмент разошлись бы в поведении (US-07 AC3).
    """
    storage = RunStorage(output_root)
    with EvidenceBundle.from_profile(profile) as bundle:
        selected, skipped = _gate_scenarios(bundle, planned)
        _require_reset_source(bundle, selected)
        adapter = HttpChatAdapter.from_profile(profile)
        try:
            _require_adapter_features(adapter, selected)
            findings = run_campaign(
                selected, RunnerDeps(adapter, bundle, telemetry=telemetry), storage, run_id,
                modes=modes, profile_ref=f"{profile.name}@{profile.version}",
                reporter_llm=reporter_llm, business=profile.business,
                trials=trials, on_event=on_event,
            )
        finally:
            adapter.close()
    return {
        "run_id": run_id,
        "run_dir": str(Path(output_root).expanduser().resolve() / run_id),
        "scenarios": [scenario.id for scenario in selected],
        "skipped": skipped,
        "asr_percent": findings["asr_percent"],
        "findings": len(findings["findings"]),
    }


def _execute_campaign(args) -> int:
    _reject_conflicting_sources(args)
    if args.from_run:
        raise PipelineConfigurationError(
            "--from пока только предпросмотр: добавьте --dry-run."
        )
    profile = load_profile(args.profile)
    campaign, planned, _ = _campaign_from_profile(args)
    run_id = new_run_id()
    if not args.json:
        print(f"прогон {run_id}: {', '.join(s.id for s in planned)}", file=sys.stderr)

    def progress(event) -> None:
        if not args.json:
            print(f"[{event.stage}] {event.message}", file=sys.stderr)

    summary = execute_campaign(
        profile, planned, campaign.modes, campaign.trials, args.output, run_id,
        reporter_llm=reporter_from_config(args.config), on_event=progress,
        telemetry=telemetry_from_config(args.config),
    )
    try:
        store = KnowledgeStore(KB_PATH)
        try:
            store.record_run(summary["run_dir"])
        finally:
            store.close()
    except Exception:
        pass
    skipped = summary["skipped"]
    if args.json:
        print(json.dumps({"ok": True, "run": summary}, ensure_ascii=False))
    else:
        print(f"{run_id}: ASR {summary['asr_percent']:.0f}% · "
              f"находок {summary['findings']} · {summary['run_dir']}")
        for note in skipped:
            print(f"пропущено: {note}")
    return 0


def _gate_scenarios(bundle, planned) -> tuple[list, list[str]]:
    """Гейт покрытия: сценарий без своего источника не запускается вовсе.

    Прогнать его было бы хуже, чем пропустить: он дал бы `not_proven`, который
    неотличим от «атака не сработала» (US-04 AC2).
    """
    selected, skipped = [], []
    for scenario in planned:
        supported, reasons = bundle.supports(scenario.goal)
        if supported:
            selected.append(scenario)
        else:
            skipped.append(f"{scenario.id}: {', '.join(reasons)}")
    if not selected:
        raise PipelineConfigurationError(
            "Ни один сценарий не покрыт источниками профиля — " + "; ".join(skipped)
        )
    return selected, skipped


def _require_adapter_features(adapter, selected) -> None:
    """Шаг фиксации памяти на цели без этой фичи сделал бы error каждой попытки."""
    if AdapterFeature.MEMORY_COMMIT in getattr(adapter, "features", frozenset()):
        return
    needing = [scenario.id for scenario in selected
               if any(step.commit_memory for step in scenario.steps)]
    if needing:
        raise PipelineConfigurationError(
            "Цель не объявляет commit_memory, а сценарии требуют фиксации памяти: "
            + ", ".join(needing)
            + ". Возьмите сценарии без шага commit_memory или объявите entrypoint.commit_memory."
        )


def _require_reset_source(bundle, selected) -> None:
    if "session_reset" in {str(kind) for kind in bundle.capabilities()}:
        return
    needing = [scenario.id for scenario in selected if scenario.reset_policy != "none"]
    if needing:
        raise PipelineConfigurationError(
            "Профиль не объявляет источник session_reset, а сценарии требуют сброса: "
            + ", ".join(needing)
            + ". Добавьте reset-провайдер или возьмите сценарии с reset_policy: none."
        )


def telemetry_from_config(config_path):
    """Наблюдаемость прогона fail-open: не поднялась — идём без неё."""
    try:
        raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        return LangfuseTelemetry(langfuse_config_from_mapping(raw.get("observability")))
    except Exception:
        return None


def reporter_from_config(config_path):
    """Нарратив отчёта необязателен и fail-open — скелет остаётся детерминированным."""
    try:
        roles = _role_configs_at(config_path)
        roles["report_writer"].validate()
        return make_llm_client(roles["report_writer"])
    except Exception:
        return None


def _campaign_from_profile(args):
    profile = load_profile(args.profile)
    specs = resolve_specs(args.scenario)
    modes = [mode.strip() for mode in (args.mode or "").split(",") if mode.strip()]
    campaign = Campaign(profile=f"{profile.name}@{profile.version}",
                        scenarios=[spec.id for spec in specs],
                        trials=args.trials, modes=modes)
    principals = profile_principals(profile)
    planned = [spec.to_planned(principals) for spec in specs]
    if args.generate:
        planned = _generate_payloads(planned, profile, args.generate, args.config)
    return campaign, planned, modes_scope(profile, modes)


def _generate_payloads(planned, profile, n, config_path):
    """US-11: заменить статические payload'ы сгенерированным списком.

    Только для сценариев с шагом payload; остальные не трогаем. Генератор —
    единственная недетерминированная точка, его список фиксируется здесь и в
    цикле прогона не пересоздаётся.
    """
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


def _campaign_from_run(reference: str):
    """US-29: повтор берётся из артефакта прогона, а не пересобирается заново."""
    run_dir = Path(reference).expanduser().resolve()
    try:
        saved = RunStorage(run_dir.parent).load_json(run_dir, "campaign.json")
        scenarios = [_planned_from_saved(item) for item in saved["scenarios"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PipelineConfigurationError(
            f"В сохранённом прогоне нет корректного campaign.json: {run_dir}"
        ) from exc
    campaign = Campaign(profile=saved.get("profile", ""),
                        scenarios=[item.id for item in scenarios],
                        trials=saved.get("trials", 1),
                        modes=list(saved.get("modes", [])))
    scope = "per_request"
    with contextlib.suppress(PipelineConfigurationError):
        scope = modes_scope(load_profile(campaign.profile), campaign.modes)
    return campaign, scenarios, scope


def _planned_from_saved(data: dict) -> PlannedScenario:
    return PlannedScenario(
        id=data["id"],
        attack_class=data.get("attack_class", ""),
        standard_refs=data.get("standard_refs", []),
        actor=data.get("actor", ""),
        payloads=data.get("payloads", []),
        goal=data.get("goal", []),
        boundary=data.get("boundary"),
        reset_policy=data.get("reset_policy", "per_scenario"),
        steps=[ScenarioStep(**step) for step in data.get("steps", [])],
    )


PROFILES_ROOT = Path(__file__).resolve().parents[1] / "profiles"

def load_profile(reference: str) -> TargetProfile:
    """`name@version` — из реестра, иначе путь к YAML (спек §12)."""
    path = Path(reference).expanduser()
    if path.is_file():
        return TargetProfile.load(path)
    name, separator, version = reference.partition("@")
    if separator:
        try:
            return ProfileRegistry(PROFILES_ROOT).load(name, version)
        except (PipelineConfigurationError, OSError) as exc:
            raise PipelineConfigurationError(
                f"Профиль {reference} не найден в реестре {PROFILES_ROOT}: {exc}"
            ) from exc
    raise PipelineConfigurationError(
        f"Профиль не найден: {reference}. Укажите путь к YAML или name@version."
    )


def profile_principals(profile: TargetProfile) -> dict[str, str]:
    """Роль сценария → значение принципала, как его объявляет профиль.

    Атрибут принципала берётся из `identities.principal`; профиль вправе его не
    дублировать, и тогда его называет первая граница изоляции.
    """
    attribute = (profile.identities.get("principal") or {}).get("attribute")
    if not attribute and profile.isolation:
        attribute = profile.isolation[0].principal_attr
    roles = profile.identities.get("roles") or {}
    return {
        role: str(values[attribute])
        for role, values in roles.items()
        if isinstance(values, Mapping) and attribute in values
    }


def modes_scope(profile: TargetProfile, modes: list[str]) -> str:
    """Переключение режима на передеплое меняет порядок исполнения (см. plan.py)."""
    for mode in modes:
        declared = profile.modes.get(mode)
        if isinstance(declared, Mapping) and declared.get("scope"):
            return str(declared["scope"])
    return "per_request"


def preview_scenario(planned) -> dict:
    return {
        "id": planned.id,
        "attack_class": planned.attack_class,
        "standard_refs": planned.standard_refs,
        "actor": planned.actor,
        "boundary": planned.boundary,
        "reset_policy": planned.reset_policy,
        "steps": [
            {"name": step.name, "actor": step.actor,
             "kind": _step_kind(step), "message": step.message}
            for step in planned.steps
        ],
        "payloads": planned.payloads,
        "goal": planned.goal,
    }


def _step_kind(step) -> str:
    if step.payload:
        return "payload"
    if step.commit_memory:
        return "commit_memory"
    return "message"


def _render_preview(payload: dict) -> str:
    campaign = payload["campaign"]
    lines = [
        f"Кампания: профиль {campaign['profile']} · сценариев {len(campaign['scenarios'])}"
        f" · прогонов на payload {campaign['trials']}"
        f" · режимы {', '.join(campaign['modes']) or '—'}",
        f"Порядок исполнения (scope={payload['modes_scope']}):",
    ]
    lines += [
        f"  {index}. {item['mode'] or '—'} · {item['scenario']}"
        for index, item in enumerate(payload["execution_order"], start=1)
    ]
    for scenario in payload["scenarios"]:
        lines += [
            "",
            f"Сценарий {scenario['id']} · {scenario['attack_class']}"
            f" · {', '.join(scenario['standard_refs']) or '—'}",
            f"  актор {scenario['actor']} · граница {scenario['boundary'] or '—'}"
            f" · reset {scenario['reset_policy']}",
            "  Шаги:",
        ]
        for index, step in enumerate(scenario["steps"], start=1):
            body = {"payload": "← payload", "commit_memory": "← фиксация памяти"}.get(
                step["kind"], step["message"] or ""
            )
            lines.append(f"    {index}. {step['name']} [{step['actor']}] {body}")
        lines.append("  Payload'ы:")
        lines += [f"    [{index}] {text}" for index, text in
                  enumerate(scenario["payloads"], start=1)]
        lines.append("  Цель:")
        lines += [f"    - {_render_assertion(item)}" for item in scenario["goal"]]
    lines += ["", "dry-run: цель не затрагивалась; будет выполнено ровно показанное."]
    return "\n".join(lines)


def _render_assertion(assertion: dict) -> str:
    rest = " ".join(f"{key}={value}" for key, value in assertion.items() if key != "type")
    return f"{assertion['type']} {rest}".strip()


# Имя плагина-провайдера → источник, который он даёт. Переедет в реестр
# провайдеров бандла (3.6); пока имена связывает CLI как composition root.
def _profile(args) -> int:
    if args.profile_command == "list":
        rows = ProfileRegistry(PROFILES_ROOT).list()
        if args.json:
            print(json.dumps({"ok": True, "profiles": [list(row) for row in rows]},
                             ensure_ascii=False))
        else:
            print("\n".join(f"{name}@{version}" for name, version in rows) or "профилей нет")
        return 0
    if args.profile_command == "diff":
        difference = profile_diff(load_profile(args.left), load_profile(args.right))
        if args.json:
            print(json.dumps({"ok": True, "diff": difference}, ensure_ascii=False))
        else:
            print(_render_diff(difference))
        return 0
    if args.profile_command == "init":
        return _profile_init(args)
    if args.profile_command in ("check", "verify"):
        return _calibrate(args, check if args.profile_command == "check" else verify)
    profile = load_profile(args.profile)
    if args.profile_command == "show":
        surface = surface_of(profile)
        print(json.dumps({"ok": True, "profile": surface}, ensure_ascii=False)
              if args.json else _render_surface(surface))
        return 0
    rows, available = coverage_of(profile, args.scenario)
    if args.json:
        print(json.dumps({"ok": True, "available_kinds": sorted(available), "coverage": rows},
                         ensure_ascii=False))
    else:
        print(_render_coverage(rows, available, profile))
    return 0


# Имена аргументов, по которым принято адресовать субъекта. Это эвристика:
# она порождает гипотезу для человека, а не факт для ядра.
PRINCIPAL_HINTS = frozenset({
    "cus", "user_id", "client_id", "customer_id", "account_id", "owner_id",
    "tenant", "tenant_id", "sub", "principal", "subject",
})
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _profile_init(args) -> int:
    """US-01: из документа берётся структура, семантику подтверждает человек."""
    if not args.offline:
        raise PipelineConfigurationError(
            "LLM-гипотезы привязок ещё не подключены (эпик ingest). "
            "Запустите с --offline: структура возьмётся из документа, "
            "семантика будет помечена TODO."
        )
    document = _read_openapi(args.openapi)
    tools, hypotheses = _tools_from_openapi(document)
    name = args.name or _slug(document.get("info", {}).get("title") or "target")
    draft = {
        "name": name,
        "version": args.version,
        "adapter": "http-chat",
        "entrypoint": {"base_url": args.base_url},
        "identities": {},
        "isolation": [],
        "surface": {"tools": tools, "memory": []},
        "modes": {},
        "evidence": [],
        "attribution": "serialized",
    }
    text = _draft_header(name, hypotheses) + yaml.safe_dump(
        draft, sort_keys=False, allow_unicode=True)
    if not args.output:
        print(text)
        return 0
    target = Path(args.output).expanduser()
    target.write_text(text, encoding="utf-8")
    if args.json:
        print(json.dumps({"ok": True, "draft": str(target), "tools": len(tools),
                          "hypotheses": hypotheses}, ensure_ascii=False))
    else:
        print(f"черновик: {target} · инструментов {len(tools)} · "
              f"гипотез к подтверждению {len(hypotheses)}")
    return 0


def _read_openapi(path: str) -> dict:
    try:
        document = yaml.safe_load(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PipelineConfigurationError(f"Не удалось прочитать OpenAPI: {path}.") from exc
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
        raise PipelineConfigurationError("OpenAPI: ожидается документ с секцией paths.")
    return document


def _tools_from_openapi(document: dict) -> tuple[list[dict], list[str]]:
    tools, hypotheses, seen = [], [], set()
    for path, operations in document["paths"].items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            name = operation.get("operationId") or "_".join(
                [method.lower(), *re.findall(r"[A-Za-z0-9]+", str(path))])
            if not isinstance(name, str) or name in seen:
                continue
            seen.add(name)
            arguments = [item["name"] for item in operation.get("parameters") or []
                         if isinstance(item, dict) and isinstance(item.get("name"), str)]
            candidate = next((a for a in arguments if a.lower() in PRINCIPAL_HINTS), None)
            tools.append({
                "name": name,
                "args": list(dict.fromkeys(arguments)),
                "sensitive": candidate is not None,
                "principal_from": {"kind": "argument", "name": candidate} if candidate
                                  else {"kind": "none"},
            })
            if candidate:
                hypotheses.append(f"{name}: принципал — аргумент '{candidate}' (угадан по имени)")
    return tools, hypotheses


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "target"


def _draft_header(name: str, hypotheses: list[str]) -> str:
    lines = [
        f"# Черновик профиля {name}. Структура взята из OpenAPI, семантика — нет.",
        "# Парсер извлекает только то, что документ утверждает: инструменты,",
        "# аргументы и точку входа. Остальное — решение человека, не вывод.",
        "#",
        "# TODO подтвердить — гипотезы по именам аргументов:",
    ]
    lines += [f"#   - {item}" for item in hypotheses] or [
        "#   - принципал не угадан ни у одного инструмента"]
    lines += [
        "#   - sensitive проставлен той же эвристикой, проверьте каждый инструмент",
        "#",
        "# TODO заполнить вручную — из документа не выводится:",
        "#   - identities: провайдер личностей и роли (attacker/victim)",
        "#   - isolation: границы изоляции и что именно они обещают",
        "#   - surface.memory: хранилища памяти, их scope и привязка записей",
        "#   - modes: уязвимый и защищённый режимы цели",
        "#   - evidence: источники наблюдения; без источника вызовов",
        "#     инструментов вердикт не поднимется выше indirect",
        "",
    ]
    return "\n".join(lines)


def _calibrate(args, calibrator) -> int:
    """Обёртка над 3.7: `check` ничего не меняет, `verify` — намеренно меняет."""
    profile = load_profile(args.profile)
    changes_state = calibrator is verify
    if changes_state and not args.json:
        print("verify меняет состояние цели: очищает память и пишет пробные маркеры.")
    with EvidenceBundle.from_profile(profile) as bundle:
        adapter = HttpChatAdapter.from_profile(profile)
        try:
            results = calibrator(bundle, adapter)
        finally:
            adapter.close()
    ok = checks_ok(results)
    if args.json:
        print(json.dumps({"ok": ok, "exit_code": 0 if ok else EXIT_PREFLIGHT,
                          "checks": [item.to_dict() for item in results]},
                         ensure_ascii=False))
    else:
        for item in results:
            print(f"[{'ок' if item.ok else 'сбой'}] {item.name}: {item.message}")
    return 0 if ok else EXIT_PREFLIGHT


def surface_of(profile: TargetProfile) -> dict:
    return {
        "name": profile.name,
        "version": profile.version,
        "adapter": profile.adapter,
        "base_url": profile.entrypoint.get("base_url"),
        "attribution": profile.attribution,
        "roles": profile.identities.get("roles", {}),
        "isolation": [{"id": b.id, "principal": b.principal_attr, "claim": b.claim}
                      for b in profile.isolation],
        "tools": [{"name": t.name, "args": t.args, "sensitive": t.sensitive,
                   "principal_from": t.principal_from} for t in profile.tools],
        "memory": [{"id": m.id, "scope": m.scope or m.scope_from,
                    "provider": m.read.get("provider")} for m in profile.memory],
        "modes": {name: mode.get("scope") for name, mode in profile.modes.items()},
        "evidence": [{"id": e.get("id"), "provider": e.get("provider"),
                      "kind": PROVIDER_KINDS.get(e.get("provider"))} for e in profile.evidence],
    }


def _available_kinds(profile: TargetProfile) -> set[str]:
    """Источники, которые профиль объявляет; память объявлена самой поверхностью."""
    kinds = {PROVIDER_KINDS[item["provider"]] for item in profile.evidence
             if item.get("provider") in PROVIDER_KINDS}
    if profile.memory:
        kinds.add("memory_snapshot")
    return kinds


def coverage_of(profile: TargetProfile, refs: list[str]) -> tuple[list[dict], set[str]]:
    """US-04: сценарий без своего источника не даст state-вердикт — сказать это заранее."""
    available = _available_kinds(profile)
    rows = []
    for spec in resolve_specs(refs):
        required = required_kinds(spec.goal)
        # То же правило, что и в EvidenceBundle.supports: state-вердикт требует
        # источника действий, память — только усилитель (US-04 AC2). Гейт нельзя
        # выполнить самим бандлом: он поднимает провайдеров, а coverage read-only.
        if any(assertion["type"] != "response_contains" for assertion in spec.goal):
            required.add("tool_calls")
        missing = sorted(required - available)
        rows.append({
            "scenario_id": spec.id,
            "attack_class": spec.attack_class,
            "required_kinds": sorted(required),
            "missing_kinds": missing,
            "reachable": "unobservable" if missing else ("state" if required else "text"),
        })
    return rows, available


def _render_surface(surface: dict) -> str:
    lines = [
        f"Профиль {surface['name']}@{surface['version']} · адаптер {surface['adapter']}"
        f" · {surface['base_url']} · атрибуция {surface['attribution']}",
        "Роли: " + (", ".join(f"{role} {values}" for role, values in surface["roles"].items()) or "—"),
        "Границы изоляции:",
    ]
    lines += [f"  {b['id']} (по {b['principal']}): {b['claim']}" for b in surface["isolation"]] or ["  —"]
    lines.append("Инструменты:")
    lines += [
        f"  {t['name']}({', '.join(t['args']) or ''})"
        f"{' · чувствительный' if t['sensitive'] else ''}"
        f" · принципал: {t['principal_from'].get('kind')}"
        f"{' ' + t['principal_from']['name'] if t['principal_from'].get('name') else ''}"
        for t in surface["tools"]
    ] or ["  —"]
    lines.append("Память:")
    lines += [f"  {m['id']} · scope {m['scope']} · {m['provider']}" for m in surface["memory"]] or ["  —"]
    lines.append("Режимы: " + (", ".join(f"{name} ({scope})" for name, scope
                                         in surface["modes"].items()) or "—"))
    lines.append("Evidence:")
    lines += [f"  {e['id']} · {e['provider']} → {e['kind'] or 'источник неизвестен'}"
              for e in surface["evidence"]] or ["  —"]
    return "\n".join(lines)


def _render_diff(difference: dict) -> str:
    if not difference:
        return "профили совпадают"
    lines = []
    for section, changes in difference.items():
        lines.append(f"{section}:")
        for label, title in (("added", "добавлено"), ("removed", "удалено")):
            for key in changes.get(label, {}):
                lines.append(f"  {title}: {key}")
        for key, values in changes.get("changed", {}).items():
            lines.append(f"  изменено: {key}: {values['before']} → {values['after']}")
    return "\n".join(lines)


def _render_coverage(rows: list[dict], available: set[str], profile: TargetProfile) -> str:
    labels = {
        "state": "state — может дать proven",
        "text": "text — потолок indirect (предикаты на тексте)",
        "unobservable": "нет источника",
    }
    lines = [
        f"Профиль {profile.name}@{profile.version} · доступные источники: "
        f"{', '.join(sorted(available)) or '—'}",
        "",
    ]
    width = max((len(row["scenario_id"]) for row in rows), default=0)
    for row in rows:
        note = labels[row["reachable"]]
        if row["missing_kinds"]:
            note += ": не хватает " + ", ".join(row["missing_kinds"])
        lines.append(f"  {row['scenario_id']:<{width}}  {note}")
    return "\n".join(lines)



def _report(args) -> int:
    """Пересобрать report.md из сохранённого findings.json — вердикт не меняется."""
    run_dir = Path(args.run).expanduser().resolve()
    storage = RunStorage(run_dir.parent)
    try:
        findings = storage.load_json(run_dir, "findings.json")
    except (OSError, ValueError) as exc:
        raise PipelineConfigurationError(
            f"В сохранённом прогоне нет корректного findings.json: {run_dir}"
        ) from exc
    output = storage.write_text(
        run_dir, "report.md",
        add_narrative(build_skeleton(findings), reporter_from_config(args.config)))
    if args.json:
        print(json.dumps({"ok": True, "report": str(output)}, ensure_ascii=False))
    else:
        print(f"отчёт: {output}")
    return 0


def _stand_sync(args) -> int:
    result = sync_stand(args.config, dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"ok": True, "sync": result.to_dict()}, ensure_ascii=False))
        return 0
    if not result.changes:
        print("стенд уже синхронизирован и проверен")
        return 0
    for change in result.changes:
        old = change.old if change.old is not None else "<нет>"
        print(f"{change.key}: {old} -> {change.new}")
    if result.dry_run:
        print("dry-run: файлы и контейнеры не изменялись")
    else:
        print("agent-api пересоздан, целевая модель проверена")
    return 0


def _serve(args) -> int:
    app = Path(__file__).parent / "ui" / "app.py"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        args.address,
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    return subprocess.run(command, check=False).returncode


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
        if args.kb_command == "status":
            return _kb_status(args, store)
        if args.kb_command == "list":
            attacks = store.all_for(args.profile)
        else:
            attacks = store.search(args.contains)
        if args.json:
            print(json.dumps({"ok": True, "attacks": attacks}, ensure_ascii=False))
        else:
            for a in attacks:
                print(f"{a['created_at']} · {a['scenario_id']} · {a['attack_class']} · "
                      f"{a['verdict']} · {a.get('status', '—')} · {a['payload']}")
        return 0
    finally:
        store.close()


def _kb_status(args, store) -> int:
    """US-36: находка живёт дальше отчёта — у неё есть статус и его история."""
    try:
        attack = store.set_status(args.attack_id, args.new_status, args.note) \
            if args.new_status else store.get(args.attack_id)
    except (UnknownStatus, KeyError) as exc:
        raise PipelineConfigurationError(str(exc).strip("'")) from exc
    history = store.status_history(args.attack_id)
    if args.json:
        print(json.dumps({"ok": True, "attack": attack, "history": history},
                         ensure_ascii=False))
    else:
        print(f"{attack['id']} · {attack['scenario_id']} · статус: {attack['status']}")
        for row in history:
            print(f"  {row['at']} → {row['status']}" + (f" ({row['note']})" if row["note"] else ""))
    return 0


def _error(message: str, json_mode: bool, code: int) -> None:
    if json_mode:
        print(json.dumps({"ok": False, "error": message, "exit_code": code}))
    else:
        print(f"ошибка: {message}", file=sys.stderr)


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("порт должен быть в диапазоне 1..65535")
    return port
