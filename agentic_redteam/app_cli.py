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
from .assertions.registry import required_kinds
from .campaign.plan import Campaign, execution_order
from .campaign.scenarios import resolve as resolve_specs
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
from .profile.diff import diff as profile_diff
from .profile.registry import ProfileRegistry
from .profile.schema import TargetProfile
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
        "--profile",
        help="профиль цели: путь к YAML (адресация name@version — с реестром профилей)",
    )
    run.add_argument(
        "--mode",
        help="режимы кампании через запятую, например vulnerable,protected (только с --profile)",
    )
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

    profile_cmd = commands.add_parser("profile", help="работа с профилями цели")
    profile_commands = profile_cmd.add_subparsers(dest="profile_command", required=True)
    for name, help_text in (
        ("list", "перечислить профили реестра"),
        ("show", "карта поверхности профиля"),
        ("diff", "различия двух версий профиля"),
        ("coverage", "что проверяемо на этой цели (гейт покрытия)"),
    ):
        sub = profile_commands.add_parser(name, help=help_text)
        if name in ("show", "coverage"):
            sub.add_argument("--profile", required=True, help="name@version или путь к YAML")
        if name == "coverage":
            sub.add_argument("--scenario", action="append", default=[],
                             help="id сценария или путь; повторяйте, по умолчанию весь каталог")
        if name == "diff":
            sub.add_argument("left", help="name@version или путь к YAML")
            sub.add_argument("right", help="name@version или путь к YAML")
        sub.add_argument("--json", action="store_true", help="вывести один JSON-результат в stdout")

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
        if args.command == "profile":
            return _profile(args)
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
    if args.profile:
        return _preview_campaign(args)
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


def _preview_campaign(args) -> int:
    """US-16: собрать кампанию из профиля и показать план с payload'ами.

    Предпросмотр не трогает цель, поэтому адаптер здесь не нужен: профиль даёт
    состав и принципалы ролей, каталог — цепочки шагов и payload'ы.
    """
    if not args.dry_run:
        raise PipelineConfigurationError(
            "Запуск по профилю пока доступен только с --dry-run: адаптер цели ещё не подключён."
        )
    profile = _load_profile(args.profile)
    specs = resolve_specs(args.scenario)
    modes = [mode.strip() for mode in (args.mode or "").split(",") if mode.strip()]
    campaign = Campaign(
        profile=f"{profile.name}@{profile.version}",
        scenarios=[spec.id for spec in specs],
        trials=args.trials,
        modes=modes,
    )
    scope = _modes_scope(profile, modes)
    principals = _profile_principals(profile)
    payload = {
        "ok": True,
        "dry_run": True,
        "campaign": asdict(campaign),
        "modes_scope": scope,
        "execution_order": [
            {"mode": mode, "scenario": scenario}
            for mode, scenario in execution_order(campaign, scope)
        ],
        "scenarios": [_preview_scenario(spec.to_planned(principals)) for spec in specs],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(_render_preview(payload))
    return 0


PROFILES_ROOT = Path(__file__).resolve().parents[1] / "profiles"


def _load_profile(reference: str) -> TargetProfile:
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


def _profile_principals(profile: TargetProfile) -> dict[str, str]:
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


def _modes_scope(profile: TargetProfile, modes: list[str]) -> str:
    """Переключение режима на передеплое меняет порядок исполнения (см. plan.py)."""
    for mode in modes:
        declared = profile.modes.get(mode)
        if isinstance(declared, Mapping) and declared.get("scope"):
            return str(declared["scope"])
    return "per_request"


def _preview_scenario(planned) -> dict:
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
PROVIDER_KINDS = {
    "log-regex": "tool_calls",
    "db-query": "memory_snapshot",
    "http-canary": "external_callback",
}


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
        difference = profile_diff(_load_profile(args.left), _load_profile(args.right))
        if args.json:
            print(json.dumps({"ok": True, "diff": difference}, ensure_ascii=False))
        else:
            print(_render_diff(difference))
        return 0
    profile = _load_profile(args.profile)
    if args.profile_command == "show":
        surface = _surface(profile)
        print(json.dumps({"ok": True, "profile": surface}, ensure_ascii=False)
              if args.json else _render_surface(surface))
        return 0
    rows, available = _coverage(profile, args.scenario)
    if args.json:
        print(json.dumps({"ok": True, "available_kinds": sorted(available), "coverage": rows},
                         ensure_ascii=False))
    else:
        print(_render_coverage(rows, available, profile))
    return 0


def _surface(profile: TargetProfile) -> dict:
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


def _coverage(profile: TargetProfile, refs: list[str]) -> tuple[list[dict], set[str]]:
    """US-04: сценарий без своего источника не даст state-вердикт — сказать это заранее."""
    available = _available_kinds(profile)
    rows = []
    for spec in resolve_specs(refs):
        required = required_kinds(spec.goal)
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
