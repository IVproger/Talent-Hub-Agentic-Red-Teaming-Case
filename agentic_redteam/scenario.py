"""Scenario model, YAML loader, and the multi-step ScenarioRunner.

A scenario is a reproducible, parameterized description of a multi-step attack.
The runner drives it against the live agent, snapshots memory around every step,
captures tool calls, and scores the result off the resulting state.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from . import scorers
from .client import AgentApiClient, mint_key
from .state import ScenarioTrace, StepTrace, ToolCall
from .tracer import StateTracer


ASSERTION_FIELDS = {
    "global_policy_written": (),
    "finalize_global_fact": (),
    "response_contains": ("step", "value"),
    "tool_cus_mismatch": ("step",),
    "tool_cus_equals": ("step", "value"),
}
SCENARIO_LIBRARY = Path(__file__).with_name("scenarios")


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
        if not isinstance(d, dict):
            raise ValueError("Scenario must be a YAML mapping.")
        scenario = cls(
            id=d["id"], name=d.get("name", d["id"]),
            attack_class=d.get("class", ""), atlas=d.get("atlas", []),
            description=d.get("description", ""), roles=d.get("roles", {}),
            params=d.get("params", {}), steps=d["steps"], goal=d.get("goal", []),
        )
        scenario.validate()
        return scenario

    def validate(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Scenario id must be a non-empty string.")
        for label, value in (
            ("name", self.name),
            ("class", self.attack_class),
            ("description", self.description),
        ):
            if not isinstance(value, str):
                raise ValueError(f"Scenario {label} must be a string.")
        if not isinstance(self.atlas, list) or any(
            not isinstance(item, str) for item in self.atlas
        ):
            raise ValueError("Scenario atlas must be a list of strings.")
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("Scenario roles must be a non-empty mapping.")
        if not isinstance(self.params, dict):
            raise ValueError("Scenario params must be a mapping.")
        if any(not isinstance(key, str) for key in self.params):
            raise ValueError("Scenario parameter names must be strings.")
        if not isinstance(self.steps, list) or not self.steps:
            raise ValueError("Scenario steps must be a non-empty list.")
        if not isinstance(self.goal, list):
            raise ValueError("Scenario goal must be a list.")

        for role, settings in self.roles.items():
            if not isinstance(role, str) or not isinstance(settings, dict):
                raise ValueError("Every scenario role must have a configuration mapping.")
            cus = settings.get("cus")
            if not isinstance(cus, (str, int)) or not str(cus).isdecimal():
                raise ValueError(f"Scenario role '{role}' must define a decimal cus.")

        step_names: set[str] = set()
        for index, step in enumerate(self.steps, start=1):
            if not isinstance(step, dict):
                raise ValueError(f"Scenario step {index} must be a mapping.")
            name = step.get("name")
            actor = step.get("actor")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Scenario step {index} must have a non-empty name.")
            if name in step_names:
                raise ValueError(f"Scenario step name '{name}' is duplicated.")
            step_names.add(name)
            if not isinstance(actor, str) or actor not in self.roles:
                raise ValueError(
                    f"Scenario step '{name}' references unknown actor '{actor}'."
                )
            if "message" in step and not isinstance(step["message"], str):
                raise ValueError(f"Scenario step '{name}' message must be a string.")
            if "finalize" in step and not isinstance(step["finalize"], bool):
                raise ValueError(f"Scenario step '{name}' finalize must be a boolean.")
            if not step.get("finalize") and "message" not in step:
                raise ValueError(
                    f"Scenario step '{name}' must define message or finalize: true."
                )
            if step.get("auth_mode", "vulnerable") not in ("vulnerable", "protected"):
                raise ValueError(
                    f"Scenario step '{name}' auth_mode must be vulnerable or protected."
                )
            if "session" in step and not isinstance(step["session"], str):
                raise ValueError(f"Scenario step '{name}' session must be a string.")
            self._validate_template(step.get("message", ""), f"step '{name}' message")

        for index, assertion in enumerate(self.goal, start=1):
            if not isinstance(assertion, dict):
                raise ValueError(f"Scenario assertion {index} must be a mapping.")
            kind = assertion.get("type")
            if kind not in ASSERTION_FIELDS:
                raise ValueError(f"Unknown scenario assertion type '{kind}'.")
            missing = [field for field in ASSERTION_FIELDS[kind] if field not in assertion]
            if missing:
                raise ValueError(
                    f"Scenario assertion {index} is missing: {', '.join(missing)}."
                )
            referenced_step = assertion.get("step")
            if referenced_step is not None and referenced_step not in step_names:
                raise ValueError(
                    f"Scenario assertion {index} references unknown step "
                    f"'{referenced_step}'."
                )
            if kind == "response_contains" and not isinstance(
                assertion.get("value"), str
            ):
                raise ValueError(
                    f"Scenario assertion {index} value must be a string."
                )
            if kind == "tool_cus_equals" and not isinstance(
                assertion.get("value"), (str, int)
            ):
                raise ValueError(
                    f"Scenario assertion {index} value must be a string or integer."
                )
            if "contains" in assertion and not isinstance(assertion["contains"], str):
                raise ValueError(
                    f"Scenario assertion {index} contains must be a string."
                )
            for field, value in assertion.items():
                if isinstance(value, str):
                    self._validate_template(value, f"assertion {index} field '{field}'")

    def _validate_template(self, text: str, label: str) -> None:
        try:
            self.render(text)
        except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"Unresolvable placeholder in {label}: {exc}") from exc

    def render(self, text: str) -> str:
        return text.format(**self.params) if text else text

    def with_runtime_values(
        self,
        attacker_cus: str,
        victim_cus: str,
        auth_mode: str,
    ) -> "Scenario":
        """Return an isolated scenario with UI/CLI identities and auth mode applied."""
        cloned = copy.deepcopy(self)
        for role, cus in (("attacker", attacker_cus), ("victim", victim_cus)):
            if role in cloned.roles:
                cloned.roles[role]["cus"] = cus
        for key, value in (
            ("attacker_cus", attacker_cus),
            ("victim_cus", victim_cus),
            ("target_cus", victim_cus),
        ):
            if key in cloned.params:
                cloned.params[key] = value
        for step in cloned.steps:
            if not step.get("finalize"):
                step["auth_mode"] = auth_mode
        cloned.validate()
        return cloned


def bundled_scenarios() -> dict[str, Scenario]:
    """Load the validated bundled scenario catalog, keyed by stable scenario id."""
    scenarios: dict[str, Scenario] = {}
    for path in sorted(SCENARIO_LIBRARY.glob("*.yaml")):
        scenario = Scenario.load(path)
        if scenario.id in scenarios:
            raise ValueError(f"Duplicate bundled scenario id: {scenario.id}")
        scenarios[scenario.id] = scenario
    return scenarios


def load_bundled_scenario(scenario_id: str) -> Scenario:
    try:
        return bundled_scenarios()[scenario_id]
    except KeyError as exc:
        raise ValueError(f"Unknown bundled scenario: {scenario_id}") from exc


ClientFactory = Callable[[str, Scenario], AgentApiClient]
StepCallback = Callable[[StepTrace, int, int], None]


class ScenarioRunner:
    def __init__(
        self,
        tracer: StateTracer | None = None,
        reset: bool = True,
        client_factory: ClientFactory | None = None,
    ):
        self.tracer = tracer or StateTracer()
        self.reset = reset
        self.client_factory = client_factory
        self._clients: dict[str, AgentApiClient] = {}
        self.last_trace: ScenarioTrace | None = None

    def _client_for(self, role: str, scenario: Scenario) -> AgentApiClient:
        if role not in self._clients:
            if self.client_factory is not None:
                self._clients[role] = self.client_factory(role, scenario)
            else:
                cus = str(scenario.roles[role]["cus"])
                self._clients[role] = AgentApiClient(
                    mint_key(cus, f"redteam-{role}"), cus
                )
        return self._clients[role]

    def run(
        self,
        scenario: Scenario,
        on_step: StepCallback | None = None,
    ) -> ScenarioTrace:
        if self.reset:
            self.tracer.reset_memory()
        self._clients.clear()
        trace = ScenarioTrace(scenario_id=scenario.id)
        self.last_trace = trace

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
            if on_step is not None:
                on_step(st, i + 1, len(scenario.steps))

        # Render placeholders (e.g. {canary}) inside assertion values before scoring.
        goal = [{k: (scenario.render(v) if isinstance(v, str) else v)
                 for k, v in a.items()} for a in scenario.goal]
        trace.scores = scorers.score(trace, goal)
        return trace
