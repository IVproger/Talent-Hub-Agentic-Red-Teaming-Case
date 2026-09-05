"""Сводка прошлых кампаний как дополнительный вход генератора (US-21).

Меняет только текст промпта генератора — не composer и не вердикт.
"""
from __future__ import annotations


def campaign_context(history: list[dict]) -> dict:
    confirmed: list[str] = []
    ineffective: list[str] = []
    prior_payloads: list[str] = []
    for entry in history:
        findings = entry.get("findings", {}) or {}
        for finding in findings.get("findings", []):
            if finding.get("verdict") == "proven":
                cls = finding.get("attack_class")
                if cls and cls not in confirmed:
                    confirmed.append(cls)
        for row in entry.get("transcript", []) or []:
            payload = row.get("payload")
            if payload and payload not in prior_payloads:
                prior_payloads.append(payload)
            if row.get("verdict") == "not_proven":
                for outcome in row.get("outcomes", []):
                    detail = outcome.get("detail")
                    if detail and detail not in ineffective:
                        ineffective.append(detail)
    return {"confirmed": confirmed, "ineffective": ineffective,
            "prior_payloads": prior_payloads}
