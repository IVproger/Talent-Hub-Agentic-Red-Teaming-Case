"""Minimal MITRE ATLAS technique reference used in reports."""

ATLAS = {
    "AML.T0051": "LLM Prompt Injection",
    "AML.T0070": "RAG Poisoning",
    "AML.T0071": "False RAG Entry Injection",
    "AML.T0061": "LLM Prompt Self-Replication",
    "AML.T0077": "LLM Response Rendering / Agent Tool Invocation",
    "AML.T0012": "Valid Accounts / Broken Access Control",
}


def describe(ids: list[str]) -> list[str]:
    return [f"{i} — {ATLAS.get(i, 'unknown technique')}" for i in ids]
