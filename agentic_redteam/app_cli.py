"""Unified human-first and script-friendly command line interface."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

import yaml

from . import __version__
from .doctor import checks_ok, run_checks
from .llm import (
    LLMConfigurationError,
    LLMRequestError,
    apply_role_overrides,
    make_llm_client,
    role_configs_from_mapping,
)
from .pipeline import (
    DEFAULT_RUNS_ROOT,
    GENERATED_BAC_SCENARIO_ID,
    PipelineConfigurationError,
    PipelineRunError,
    RunConfig,
    load_effective_config,
    regenerate_report,
    run_pipeline,
    sanitize_error,
)
from .scenario import Scenario, bundled_scenarios
from .stand_sync import StandSyncError, sync_stand
from .target_runtime import TargetConfigurationError


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
            "Примеры: python -m agentic_redteam doctor; "
            "python -m agentic_redteam run --scenario generated-bac"
        ),
    )
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="проверить локальное окружение, ничего не меняя")
    _add_config_path(doctor)
    doctor.add_argument("--offline", action="store_true", help="проверять только файлы и конфигурацию")
    doctor.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    run = commands.add_parser("run", help="запустить генерируемые или встроенные сценарии безопасности")
    _add_config_path(run)
    run.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="id сценария или путь к YAML; повторяйте для нескольких",
    )
    run.add_argument("-n", "--trials", type=int, default=1, help="прогонов на сценарий (по умолчанию: 1)")
    run.add_argument("--attacker-cus")
    run.add_argument("--victim-cus")
    run.add_argument("--auth-mode", choices=("vulnerable", "protected"))
    run.add_argument(
        "--arch", help="файл архитектуры (.mmd) для контекста Adaptive BAC"
    )
    run.add_argument(
        "--system-card",
        help="файл описания компонентов (system card) для контекста Adaptive BAC",
    )
    run.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_RUNS_ROOT),
        help="корневой каталог для артефактов запусков",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="показать итоговую конфигурацию (с редактированием секретов) без запуска",
    )
    run.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    report = commands.add_parser("report", help="пересобрать отчёт из сохранённого запуска")
    report.add_argument("--run", required=True, help="каталог сохранённого запуска")
    report.add_argument("--report-provider", choices=("ollama", "openrouter"))
    report.add_argument("--report-model")
    report.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

    stand = commands.add_parser("stand", help="управление настроенным целевым стендом")
    stand_commands = stand.add_subparsers(dest="stand_command", required=True)
    stand_sync = stand_commands.add_parser(
        "sync", help="применить llm.target_agent из YAML в stand/.env"
    )
    _add_config_path(stand_sync)
    stand_sync.add_argument(
        "--dry-run", action="store_true", help="показать управляемые изменения без записи"
    )
    stand_sync.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

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
    config_path = Path(args.config)
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
        if args.command == "report":
            return _report(args)
        if args.command == "stand" and args.stand_command == "sync":
            return _stand_sync(args)
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
    except PipelineRunError as exc:
        payload = {
            "ok": False,
            "error": sanitize_error(exc),
            "exit_code": EXIT_PIPELINE,
            "run": asdict(exc.result) if exc.result else None,
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"ошибка: {exc}", file=sys.stderr)
            if exc.result:
                print(f"запуск: {exc.result.run_dir}", file=sys.stderr)
        return EXIT_PIPELINE
    except KeyboardInterrupt:
        print("Прервано.", file=sys.stderr)
        return 130
    except Exception as exc:  # keep expected operational failures concise
        _error(sanitize_error(exc), getattr(args, "json", False), EXIT_PIPELINE)
        return EXIT_PIPELINE
    return 0


def _doctor(args) -> int:
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
    scenario_ids = _resolve_scenario_ids(args.scenario)
    roles = _role_configs(args)
    context_overrides = {}
    if args.arch is not None:
        context_overrides["arch"] = Path(args.arch)
    if args.system_card is not None:
        context_overrides["system_card"] = Path(args.system_card)
    configs = [
        RunConfig(
            target_config=Path(args.config),
            **context_overrides,
            output_root=Path(args.output),
            num_candidates=args.trials,
            attacker_cus=args.attacker_cus,
            victim_cus=args.victim_cus,
            auth_mode=args.auth_mode,
            llm_roles=roles,
            scenario_id=scenario_id,
        )
        for scenario_id in scenario_ids
    ]
    if args.dry_run:
        effective = [load_effective_config(config)["safe"] for config in configs]
        payload = {"ok": True, "dry_run": True, "configurations": effective}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        return 0
    results = []
    for config in configs:
        if not args.json:
            print(
                f"запуск {config.scenario_id} ({args.trials} прогон(ов))",
                file=sys.stderr,
            )

        def progress(event) -> None:
            if not args.json:
                print(f"[{event.stage}] {event.message}", file=sys.stderr)

        result = run_pipeline(
            config,
            on_event=progress,
        )
        results.append(result)
    if args.json:
        print(
            json.dumps(
                {"ok": True, "runs": [asdict(result) for result in results]},
                ensure_ascii=False,
            )
        )
    else:
        for result in results:
            print(
                f"{result.scenario_id}: {result.status} · "
                f"ASR {result.asr_percent:.0f}% · {result.run_dir}"
            )
    return 0


def _resolve_scenario_ids(values: list[str]) -> list[str]:
    try:
        catalog = bundled_scenarios()
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        raise PipelineConfigurationError("Не удалось загрузить встроенные сценарии.") from exc
    available = {GENERATED_BAC_SCENARIO_ID, *catalog}
    if not values:
        return [GENERATED_BAC_SCENARIO_ID, *catalog]
    resolved: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_file():
            try:
                scenario_id = Scenario.load(path).id
            except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
                raise PipelineConfigurationError(
                    f"Не удалось загрузить конфигурацию сценария: {path}"
                ) from exc
        else:
            scenario_id = value
        if scenario_id not in available:
            raise PipelineConfigurationError(
                f"Неизвестный сценарий '{scenario_id}'. Доступные: "
                + ", ".join(sorted(available))
            )
        if scenario_id not in resolved:
            resolved.append(scenario_id)
    return resolved


def _report(args) -> int:
    run_dir = Path(args.run).expanduser().resolve()
    try:
        saved = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        roles = role_configs_from_mapping(saved.get("llm"))
    except (OSError, ValueError) as exc:
        raise PipelineConfigurationError(f"В сохранённом запуске нет корректного config.json: {run_dir}") from exc
    roles = apply_role_overrides(
        roles,
        {"report_writer": {"provider": args.report_provider, "model": args.report_model}},
    )
    roles["report_writer"].validate()
    output = regenerate_report(run_dir, make_llm_client(roles["report_writer"]))
    if args.json:
        print(json.dumps({"ok": True, "report": str(output)}))
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
