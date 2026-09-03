"""Scenario model, YAML loader, and the multi-step ScenarioRunner.

A scenario is a reproducible, parameterized description of a multi-step attack.
The runner drives it against the live agent, snapshots memory around every step,
captures tool calls, and scores the result off the resulting state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import scorers
from .client import AgentApiClient, mint_key
from .state import ScenarioTrace, StepTrace, ToolCall
from .tracer import StateTracer


@dataclass
class Scenario:
    id: str
    name: str
    attack_class: str
    atlas: list[str]
    description: str
    roles: dict[str, dict]
    params: dict[str, Any]
    steps: list[dict]
    goal: list[dict]

    @classmethod
    def load(cls, path: str | Path) -> "Scenario":
        d = yaml.safe_load(Path(path).read_text())
        return cls(
            id=d["id"], name=d.get("name", d["id"]),
            attack_class=d.get("class", ""), atlas=d.get("atlas", []),
            description=d.get("description", ""), roles=d.get("roles", {}),
            params=d.get("params", {}), steps=d["steps"], goal=d.get("goal", []),
        )

    def render(self, text: str) -> str:
        return text.format(**self.params) if text else text


class ScenarioRunner:
    def __init__(self, tracer: StateTracer | None = None, reset: bool = True):
        self.tracer = tracer or StateTracer()
        self.reset = reset
        self._clients: dict[str, AgentApiClient] = {}

    def _client_for(self, role: str, scenario: Scenario) -> AgentApiClient:
        if role not in self._clients:
            cus = str(scenario.roles[role]["cus"])
            self._clients[role] = AgentApiClient(mint_key(cus, f"redteam-{role}"), cus)
        return self._clients[role]

    def run(self, scenario: Scenario) -> ScenarioTrace:
        if self.reset:
            self.tracer.reset_memory()
        self._clients.clear()
        trace = ScenarioTrace(scenario_id=scenario.id)

        for i, step in enumerate(scenario.steps):
            role = step["actor"]
            client = self._client_for(role, scenario)
            session_id = step.get("session", f"{scenario.id}-{role}")
            st = StepTrace(name=step["name"], actor_cus=client.cus,
                           request=scenario.render(step.get("message", "")))
            st.memory_before = self.tracer.snapshot_memory()
            mark = self.tracer.log_marker()

            if step.get("finalize"):
                st.finalize_facts = client.finalize(session_id)
                st.response = f"[finalized: {len(st.finalize_facts)} facts]"
            else:
                st.response = client.chat(
                    st.request, session_id, auth_mode=step.get("auth_mode", "vulnerable"),
                )

            st.tool_calls = self.tracer.tool_calls_since(mark)
            st.memory_after = self.tracer.snapshot_memory()
            trace.steps.append(st)

        # Render placeholders (e.g. {canary}) inside assertion values before scoring.
        goal = [{k: (scenario.render(v) if isinstance(v, str) else v)
                 for k, v in a.items()} for a in scenario.goal]
        trace.scores = scorers.score(trace, goal)
        return trace
