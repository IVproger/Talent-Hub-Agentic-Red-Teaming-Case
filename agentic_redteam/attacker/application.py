"""Application layer for autonomous AttackBrief campaigns.

The CLI supplies user-facing configuration and output formatting; this module
owns validation and assembly of the target adapter, evidence bundle, attacker
dependencies, and campaign runner.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from ..adapters.http_chat import HttpChatAdapter
from ..doctor import checks_ok
from ..errors import PipelineConfigurationError
from ..evidence.bundle import EvidenceBundle
from ..evidence.calibrate import check
from ..profile.schema import TargetProfile
from ..storage.runs import RunStorage
from ..target_runtime import TargetConfigurationError
from .agent import AttackerDeps, AttackerLimits
from .briefs import AttackBrief
from .campaign import CAMPAIGN_STRATEGIES, run_attack_campaign


def limits_from_config(config: Mapping[str, Any] | None) -> AttackerLimits:
    """Parse and validate autonomous-attempt limits from configuration."""
    raw = (config or {}).get("attacker")
    if raw is None:
        return AttackerLimits()
    if not isinstance(raw, Mapping):
        raise PipelineConfigurationError("attacker — ожидается отображение.")
    known = set(AttackerLimits.__dataclass_fields__)
    unknown = set(raw) - known
    if unknown:
        raise PipelineConfigurationError(
            "attacker — неизвестные поля: " + ", ".join(sorted(unknown))
        )
    values = {field: getattr(AttackerLimits(), field) for field in known}
    for field, value in raw.items():
        if field in {
            "max_turns", "llm_retries", "experience_max_attempts",
            "experience_max_chars",
        }:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise PipelineConfigurationError(
                    f"attacker.{field} — ожидается положительное целое число."
                )
            values[field] = value
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise PipelineConfigurationError(
                f"attacker.{field} — ожидается положительное число."
            )
        values[field] = value
    return AttackerLimits(**values)


def validate_campaign_inputs(
    profile: TargetProfile,
    briefs: list[AttackBrief],
    modes: list[str] | None,
    trials: int,
    strategy: str = "independent",
    stop_on_success: bool = False,
) -> None:
    """Validate a frozen brief set against the exact target being attacked."""
    if profile.entrypoint.get("review_required"):
        raise PipelineConfigurationError(
            "Неподтверждённый черновик: заполните привязки и очистите "
            "entrypoint.review_required."
        )
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise PipelineConfigurationError("--trials должен быть положительным целым числом.")
    if strategy not in CAMPAIGN_STRATEGIES:
        raise PipelineConfigurationError(f"Неизвестная стратегия кампании: {strategy}")
    if stop_on_success and strategy != "adaptive":
        raise PipelineConfigurationError(
            "--stop-on-success используется только с --strategy adaptive."
        )
    for mode in modes or []:
        if profile.modes and mode not in profile.modes:
            raise PipelineConfigurationError(f"Режим '{mode}' не объявлен в профиле.")
    for brief in briefs:
        brief.validate_against_profile(profile)


def execute_attack_campaign(
    profile: TargetProfile,
    briefs: list[AttackBrief],
    attacker_llm: Any,
    judge: Any,
    storage: RunStorage,
    run_id: str,
    *,
    modes: list[str] | None,
    trials: int,
    limits: AttackerLimits,
    config: dict | None = None,
    authorization: dict | None = None,
    telemetry: Any = None,
    on_event: Callable | None = None,
    metadata: dict | None = None,
    strategy: str = "independent",
    stop_on_success: bool = False,
) -> dict:
    """Validate, assemble, and execute one autonomous campaign."""
    briefs = list(briefs)
    validate_campaign_inputs(
        profile, briefs, modes, trials, strategy, stop_on_success,
    )
    campaign_metadata = dict(metadata or {})
    if authorization is not None:
        campaign_metadata["authorization"] = authorization

    with EvidenceBundle.from_profile(profile) as bundle:
        if "session_reset" not in {str(kind) for kind in bundle.capabilities()}:
            raise PipelineConfigurationError(
                "Автономная кампания требует reset-провайдера в профиле "
                "(сброс состояния перед каждой попыткой)."
            )
        adapter = HttpChatAdapter.from_profile(profile, telemetry=telemetry)
        try:
            preflight = (
                check(bundle, adapter)
                if isinstance(getattr(bundle, "providers", None), Mapping)
                else adapter.preflight()
            )
            if not checks_ok(preflight):
                raise TargetConfigurationError(
                    "; ".join(
                        item.message for item in preflight
                        if not item.ok and item.blocking
                    )
                )
            profile_roles = tuple(
                (profile.identities.get("roles", {}) or {"attacker": {}}).keys()
            )
            deps = AttackerDeps(
                adapter=adapter,
                evidence=bundle,
                llm=attacker_llm,
                roles=profile_roles,
                supports_memory_commit="commit_memory" in profile.entrypoint,
                telemetry=telemetry,
            )
            return run_attack_campaign(
                briefs,
                deps,
                judge,
                storage,
                run_id,
                modes=modes or None,
                trials=trials,
                limits=limits,
                profile=profile,
                profile_ref=f"{profile.name}@{profile.version}",
                config=config,
                on_event=on_event,
                metadata=campaign_metadata,
                strategy=strategy,
                stop_on_success=stop_on_success,
            )
        finally:
            adapter.close()
