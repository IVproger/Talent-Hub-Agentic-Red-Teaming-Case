"""State models for the agent-state trace.

The core idea of this tool: a compromise is detected in the agent's *state*
(a poisoned global-policy write, a tool call with someone else's cus), not in the
final chat text. These models capture snapshots and per-step traces so scoring and
reporting work off state, not off the response string.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemorySnapshot:
    """A point-in-time view of the agent's long-term memory."""
    collections: dict[str, list[dict]] = field(default_factory=dict)

    def global_policies(self) -> list[str]:
        """Statements in the cross-user global-policy store."""
        docs = self.collections.get("agent_policy_memories", [])
        return [d.get("statement", "") for d in docs]

    def count(self, collection: str) -> int:
        return len(self.collections.get(collection, []))


@dataclass
class ToolCall:
    """A single tool invocation observed in the trace (cus = chosen argument)."""
    tool: str
    cus: str


@dataclass
class StepTrace:
    """One step of a scenario (inject / finalize / activate)."""
    name: str
    actor_cus: str
    request: str
    response: str = ""
    finalize_facts: list[dict] = field(default_factory=list)  # facts with scope, from finalize
    tool_calls: list[ToolCall] = field(default_factory=list)
    memory_before: MemorySnapshot | None = None
    memory_after: MemorySnapshot | None = None

    def new_global_policies(self) -> list[str]:
        """Global policies that appeared during this step (the poisoning write)."""
        if not (self.memory_before and self.memory_after):
            return []
        before = set(self.memory_before.global_policies())
        return [p for p in self.memory_after.global_policies() if p not in before]


@dataclass
class ScenarioTrace:
    """Full multi-step trace of one scenario run."""
    scenario_id: str
    steps: list[StepTrace] = field(default_factory=list)
    scores: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return bool(self.scores.get("success"))

    def all_tool_calls(self) -> list[ToolCall]:
        return [tc for s in self.steps for tc in s.tool_calls]
