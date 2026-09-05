"""Campaign model and execution ordering.

`execution_order` groups by mode when switching a mode requires a redeploy
(`per_deployment`), else interleaves modes per scenario (`per_request`).
No target specifics live here — profile/scenarios/modes are plain identifiers.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Campaign:
    profile: str                       # "name@version" reference
    scenarios: list[str]
    trials: int = 1
    modes: list[str] = field(default_factory=list)


def execution_order(campaign: Campaign, modes_scope: str) -> list[tuple[str | None, str]]:
    modes: list[str | None] = list(campaign.modes) or [None]
    if modes_scope == "per_deployment":
        return [(m, s) for m in modes for s in campaign.scenarios]
    return [(m, s) for s in campaign.scenarios for m in modes]
