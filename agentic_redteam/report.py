"""Render scenario traces into a Markdown red-team report."""
from __future__ import annotations

from .atlas import describe
from .scenario import Scenario
from .state import ScenarioTrace


def _step_md(st) -> list[str]:
    out = [f"### Step `{st.name}` (actor cus={st.actor_cus})"]
    if st.request:
        out.append(f"- **request:** {st.request[:300]}")
    if st.finalize_facts:
        globals_ = [f for f in st.finalize_facts if f.get('scope') == 'global']
        out.append(f"- **finalize:** {len(st.finalize_facts)} facts, "
                   f"{len(globals_)} tagged `global`")
    else:
        out.append(f"- **response:** {st.response[:300].strip()}")
    if st.tool_calls:
        out.append(f"- **tool calls:** " +
                   ", ".join(f"{tc.tool}(cus={tc.cus})" for tc in st.tool_calls))
    new_pol = st.new_global_policies()
    if new_pol:
        out.append(f"- **⚠ new GLOBAL policy written:** {new_pol}")
    return out


def render(scenario: Scenario, trace: ScenarioTrace) -> str:
    verdict = "✅ COMPROMISED" if trace.success else "❌ not compromised"
    lines = [
        f"# {scenario.name}",
        f"**Scenario:** `{scenario.id}` · **class:** {scenario.attack_class}",
        f"**Verdict:** {verdict}",
        "",
        f"> {scenario.description.strip()}",
        "",
        "**MITRE ATLAS:** " + "; ".join(describe(scenario.atlas)),
        "",
        "## Trace",
    ]
    for st in trace.steps:
        lines += _step_md(st)
    lines += ["", "## Goal assertions (state-based)"]
    for a in trace.scores["assertions"]:
        mark = "✅" if a["passed"] else "❌"
        lines.append(f"- {mark} `{a['type']}` — {a['detail']}")
    return "\n".join(lines) + "\n"


def _representative(traces: list[ScenarioTrace]) -> ScenarioTrace:
    """Prefer a successful trace to illustrate the scenario; else the first."""
    for t in traces:
        if t.success:
            return t
    return traces[0]


def summary(results: list[tuple[Scenario, list[ScenarioTrace]]]) -> str:
    total_trials = sum(len(ts) for _, ts in results)
    total_ok = sum(1 for _, ts in results for t in ts if t.success)
    asr = (total_ok / total_trials * 100) if total_trials else 0.0

    lines = ["# Agentic Red-Team Report", "",
             f"**Attack Success Rate (ASR): {asr:.0f}%** "
             f"({total_ok}/{total_trials} trials succeeded across {len(results)} scenarios)",
             "", "| Scenario | Class | Trials | Success | ASR |",
             "|---|---|---|---|---|"]
    for s, ts in results:
        ok = sum(1 for t in ts if t.success)
        rate = (ok / len(ts) * 100) if ts else 0.0
        lines.append(f"| {s.id} | {s.attack_class} | {len(ts)} | {ok} | {rate:.0f}% |")
    lines.append("")
    for s, ts in results:
        ok = sum(1 for t in ts if t.success)
        lines.append(f"_Scenario ASR: {ok}/{len(ts)} trials. Representative trace below._\n")
        lines.append(render(s, _representative(ts)))
        lines.append("\n---\n")
    return "\n".join(lines)
