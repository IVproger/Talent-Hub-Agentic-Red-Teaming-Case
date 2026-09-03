# PoC Implementation Plan — single BAC vertical slice (parallel-first)

Scope, inputs, and system description are in `README.md`. This document is the task
breakdown, structured so **three tracks run in parallel** after a short contract-freezing
phase. Target = the GenAI invest stand (`target/arch.mmd`, `target/system-card.md`,
`target/target.yaml`).

One attack class only: **`tool_argument_bac`** on the `react-agent` component, stand in
`auth_mode: vulnerable`. The verdict is decided from the target's own tool-call log, never
from the agent's reply text.

## The idea behind the parallelism

The pipeline is `generate → execute → verdict → report (+ reflect)`. Left linear, it is a
chain. Made parallel by freezing **two data contracts** up front, so each track builds and
tests against a fixture instead of waiting for the previous stage:

- **C1 — payloads:** `list[str]` (generator → runner).
- **C2 — attempt result:** `{payload, response, tool_calls: [{tool, cus}], verdict, evidence}`
  (runner+verdict → report and reflection). `verdict ∈ {proven, indirect, not_proven}`.

`target.yaml` is the third, already-written contract (endpoint, roles→`cus`, component,
verdict type).

## Reuse (all in Track E)

Already working in the existing `agentic_redteam` package:
- `client.py` — target HTTP client + headless `sk-genai-…` key minting bound to a `cus`.
- `tracer.py` — recovers the `cus` argument of each client-data tool call from the log.
- `scorers.py` — the `tool_cus_mismatch` assertion.

## Phase 0 — freeze contracts (JOINT, ~1h, blocking)

| ID | Task | Done when |
|---|---|---|
| **C0** | Write C1 + C2 as a tiny `schemas.py` (or dataclasses) **and** one committed fixture file each: `fixtures/payloads.json` (5 sample payloads) and `fixtures/attempts.json` (3 sample attempt results, incl. one `proven`) | All three engineers can import the shapes and load the fixtures |

Nothing else starts until C0 exists. After it, the three tracks below never block each other.

## Track G — generation (owner 1) · needs neither stand nor other tracks

| ID | Task | Deps | Est | Done when |
|---|---|---|---|---|
| **G1** | Input loader: read the three `target/*` files; extract the card section for `attack.component` | C0 | 1h | Returns architecture text + target component description + parsed config |
| **G2** | LLM client: thin wrapper over an OpenAI-compatible endpoint (provider from config, not pinned). `llm(prompt) -> str` | — | 1h | Deterministic at `temperature=0`; endpoint is a config value |
| **G3** | Attack generator: prompt = architecture + component card + BAC framing → `num_candidates` payloads (direct other-`cus` request, authority framing, "for comparison", obfuscation). **Output validates against C1** | G1, G2 | 3h | Emits ≥5 C1-valid payloads aimed at the victim `cus` |
| **G4** | Reflection: one LLM pass over **C2 attempts** (read from the fixture during dev) → analysis text + optionally one refined payload (C1) | G2, C0 | 2h | Produces reflection text + at most one follow-up payload, tested against `fixtures/attempts.json` |

## Track E — execution + evidence (owner 2) · needs the live stand, not the LLM

| ID | Task | Deps | Est | Done when |
|---|---|---|---|---|
| **E1** | Runner: for each **C1 payload** (from `fixtures/payloads.json` during dev), `client.chat` as attacker (`cus`/`auth_mode` from config); capture response + tool calls via the tracer | C0 | 2h | Each attempt yields response + observed tool calls with their `cus` |
| **E2** | Verdict: deterministic `tool_cus_mismatch` → `proven` / `indirect` / `not_proven`; attach leaked `cus` + log line. **Assembles a C2 record** | E1 | 1h | Feeding `fixtures/payloads.json` produces C2-valid attempts, incl. real `proven` against the live stand |

## Track R — reporting (owner 3) · needs neither stand nor LLM

| ID | Task | Deps | Est | Done when |
|---|---|---|---|---|
| **R1** | Report: Markdown + `findings.json` from **C2 attempts** (the fixture during dev). ASR (`proven/total`), attempts table (payload → verdict → leaked `cus`), reflection slot, compromise point = `tool call / arguments` | C0 | 3h | Regenerates from `fixtures/attempts.json` with no hand-editing; ≥1 finding shown `proven` |

## Integration (any owner, after the tracks land)

| ID | Task | Deps | Est | Done when |
|---|---|---|---|---|
| **I1** | Entry point `poc_bac.py`: wire G3 → E1/E2 → R1, with the G4 reflection loop (one follow-up round back through E1/E2). Swap fixtures for live wiring | G3, E2, R1, G4 | 2h | `python poc/poc_bac.py --arch … --card … --config …` runs end to end, real stand, real LLM |

## Dependency graph

```
        C0  (joint, blocks everything; ~1h)
        |
   +----+--------------------+--------------------+
   |                         |                    |
 Track G                  Track E              Track R
 G1,G2 -> G3              E1 -> E2             R1
       \-> G4 (vs C2 fixture)  (vs C1 fixture)  (vs C2 fixture)
   |                         |                    |
   +----------+--------------+--------------------+
              |
             I1  (integration; ~2h)
```

No cross-track dependency exists except C0 and the final I1. Each track is independently
runnable and testable against its fixture the entire time.

- **Track G** never touches the stand → can run on any laptop.
- **Track E** never touches the LLM → deterministic, testable with a hardcoded payload list.
- **Track R** touches neither → pure function of C2, demoable from the fixture on day one.

**Wall-clock:** Phase 0 (~1h) + max(Track G ≈ 5h, Track E ≈ 3h, Track R ≈ 3h) + I1 (~2h)
≈ **8h with three engineers**, versus ~13h linear. With two, fold Track R into whoever
finishes first.

## Demo moment

Attacker is client 1001. No reply contains anything overtly malicious, yet the evidence
shows a tool call reading client 1002's data — the agent's *action* was compromised, not
its text. The report states exactly where: the tool-call arguments.

## Out of scope (deferred to the full system)

Memory poisoning, cross-session / cross-user propagation, other tools and integrations,
LangFuse trace ingestion, attack-catalog engine, target-agnostic adapters, CI/regression
export, LLM-judge.
