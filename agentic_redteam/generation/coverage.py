"""Отчёт о покрытии из гейтов composer — честная карта проверяемого."""
from __future__ import annotations

from dataclasses import dataclass

from ..profile.schema import TargetProfile
from .composer import Unsupported, compose, profile_capabilities
from .template import Template


@dataclass(frozen=True)
class CoverageRow:
    template_id: str
    standard: str
    status: str
    reason: str
    ceiling: str


@dataclass(frozen=True)
class CoverageReport:
    rows: list[CoverageRow]

    def composed(self) -> list[str]:
        return [row.template_id for row in self.rows if row.status == "composed"]

    def excluded(self) -> list["CoverageRow"]:
        return [row for row in self.rows if row.status != "composed"]


def coverage(templates: list[Template], profile: TargetProfile) -> CoverageReport:
    capabilities = profile_capabilities(profile)
    rows = []
    for template in templates:
        standard = template.standard.get("asi") or template.standard.get("llm") or template.id
        result = compose(template, profile, capabilities)
        if isinstance(result, Unsupported):
            rows.append(CoverageRow(template.id, str(standard), result.kind, result.reason, ""))
        else:
            text_only = all(a["type"] == "response_contains" for a in result.goal)
            ceiling = "indirect" if text_only else "proven"
            rows.append(CoverageRow(template.id, str(standard), "composed", "", ceiling))
    return CoverageReport(rows)
