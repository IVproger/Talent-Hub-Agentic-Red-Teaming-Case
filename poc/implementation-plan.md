# Implementation Plan — full-system architecture, single-attack execution

This is the **full-system** design (aligned to the 8-step plan: stand → LangFuse →
reverse-engineering → descriptor engine → per-component attack generation → run loop with
trace capture → knowledge DB → report). For the hackathon we **execute the whole pipeline
end to end on ONE attack** — Broken Access Control on the `react-agent` component — with the
agent descriptor **supplied as a prepared input** (`target/arch.mmd` + `target/system-card.md`),
not auto-derived. LangFuse, the deterministic verdict, the knowledge DB and the LLM-written
report are all real; only breadth (one component, one attack) and the descriptor **engine**
are reduced.

## Scoping at a glance

| Ivan's step | Full system | This run |
|---|---|---|
| 1. Deploy & configure stand | any target | ✅ done — stand as submodule under `stand/` |
| 2. Attach LangFuse | trace every agent | **implement** (v2 = 2 containers) |
| 3. Reverse-engineer → arch/spec/TZ | per target | ✅ **prepared** — `arch.mmd`, `system-card.md` |
| Sys-1. Engine: docs + live MCP/API introspection → BIG `AgentDescriptor` JSON | build | **deferred** — descriptor is a prepared input; only a loader that reads the prepared docs into the JSON is built |
| Sys-2. Per-component → attack-spec JSON | all components | **one** component (`react-agent`), one class (`tool_argument_bac`) |
| Sys-3. Run loop → LangFuse trace + verdict → knowledge DB | all specs | the BAC spec(s) |
| Sys-4. LLM scans knowledge DB → tech report | full report | report for this run |

Everything marked "deferred/one/prepared" is a breadth reduction, not a shape change: the
pipeline runs through every stage.

## The spine — three contracts

1. **`AgentDescriptor`** (the BIG JSON). Fields: identity/version; API contract (endpoints,
   auth, extra body fields like `auth_mode`); roles & identity model; tools (name, arg
   schema, side-effect class, data scope); memory architecture (levels, store, scope, TTL,
   read path, write path); integrations (MCP/web/DB); trace sources. **Schema is defined
   now; the instance for the stand is hand-written** from the prepared arch + card. The
   full-system engine that auto-produces it (LLM synthesis over docs + live `tools/list`
   introspection) is post-hackathon.
2. **`AttackSpec`** (per component). Fields: id, family, component ref into the descriptor,
   preconditions, delivery channel, steps, `success_criteria[]` (deterministic), evidence
   required, compromise point, ATLAS/OWASP refs.
3. **`KnowledgeRecord`** (one row of the knowledge DB). Fields: attack spec, run provenance
   (target model, stand SHA, descriptor hash, timestamps), **LangFuse trace id**, the agent
   trace pulled from LangFuse (LLM calls, prompt incl. injected memory, tool calls with full
   args, ordering), deterministic evidence (memory/DB diff, tool-call `cus`), verdict
   (`proven` / `indirect` / `not_proven`), compromise point, severity.

## Verifiability principle (do not violate)

The **deterministic collector is the verdict authority** — it reads the target's own state
(MongoDB memory, invest-server tool-call log) independently of what the agent reports.
**LangFuse is the rich trace** that localizes *where* in the chain the compromise happened
and the substrate the report LLM scans. Both, never either/or: an agent-self-reported trace
must not decide success.

## Tasks (parallel-friendly)

### Phase 0 — freeze the three schemas (JOINT, ~2h, blocking)
- **S0** — write `AgentDescriptor`, `AttackSpec`, `KnowledgeRecord` as JSON Schemas + one
  fixture each (a hand-written stand descriptor, one BAC AttackSpec, one sample
  KnowledgeRecord incl. a LangFuse trace id). *Done when* all tracks can load the fixtures.

### Track P — prep (owner 1)
- **P1** LangFuse v2 up (`langfuse/langfuse:2` + postgres); project + API keys. *Done when* UI reachable, self-hosted (in-perimeter).
- **P2** Instrument the stand: pass `config={"callbacks":[handler],"metadata":{...}}` at the LLM/tool call sites (`app/agent/runner.py:201` LLM, `:215` `tool.ainvoke(args)` — full args, `:221` wrap-up; `app/orchestrator/graph.py:172`); propagate `run_id`/`step`/`cus`. *Done when* one manual chat yields a LangFuse trace showing the LLM call, the system prompt incl. injected memory, and each tool call with full arguments.
- **P3** Descriptor loader: read the prepared `arch.mmd` + `system-card.md` + `target.yaml` into a validated `AgentDescriptor` JSON (the prepared-input stand-in for the Sys-1 engine). *Done when* it emits a schema-valid descriptor for the stand.

### Track G — generation (owner 2) · no stand needed
- **G1** From the descriptor's `react-agent` component + `tool_argument_bac` class → one or
  more `AttackSpec` JSON (LLM writes payload text/steps; success criteria come from the
  attack template, not free-form). *Done when* ≥1 schema-valid AttackSpec with deterministic criteria.

### Track E — execution + evidence + knowledge DB (owner 3) · reuses existing collector
- **E1** Runner: consume an `AttackSpec`, drive `client.py` as the attacker identity,
  capture response + tool calls via `tracer.py`; grab the LangFuse `trace_id` for the run. *Done when* each attempt yields response, tool-call `cus`, and a trace id.
- **E2** Verdict: deterministic `tool_cus_mismatch` → `proven` / `indirect` / `not_proven`;
  attach evidence. *Done when* a real `proven` is produced against the live stand.
- **E3** Knowledge DB: SQLite (or JSONL) storing `KnowledgeRecord`s (attack, verdict,
  evidence, provenance, LangFuse trace ref). Append-only, queryable. *Done when* a run
  survives process exit and is queryable by verdict/compromise point.

### Track R — report (owner 4, or fold in) · reads the knowledge DB
- **R1** LLM scans the knowledge DB (records + linked LangFuse traces) → tech report
  (Markdown/HTML + `findings.json`): ASR, per-finding evidence, the agent timeline from
  LangFuse, **compromise point localized** (retrieval / decision / tool call), severity,
  reproduction conditions. *Done when* it regenerates from the DB with no hand-editing and
  localizes the BAC compromise at the tool-call arguments.

### Integration
- **I1** `poc_bac.py`: S0 → P3/G1 → E1/E2/E3 → R1 end to end on the live stand + LangFuse.

## Dependency graph

```
                 S0  (schemas; blocks all)
                  |
   +--------+-----+------+---------------+
   |        |            |               |
 P1->P2    P3           G1              (E waits on P2 for trace ids,
   |        |            |                on S0 for shapes)
   +----+---+------+-----+
        |          |
       E1 -> E2 -> E3 -> R1 -> I1
```

Track G and P3 need no stand; Track R is a pure function of the knowledge DB (demoable from
the S0 fixture on day one). The only hard cross-links: S0 (all), P2 → E1 (trace ids), E3 → R1.

## Demo moment

One BAC attack, all the way through the real pipeline: **LangFuse** shows the agent's chain
(system prompt incl. memory, the tool call issued with `cus=1002` arguments); the
**deterministic collector** proves client 1002's data was actually read; the **knowledge DB**
stores the record; the **report LLM** scans it and writes up the finding, localizing the
compromise at the tool-call arguments — no malicious text anywhere in the reply.

## Deferred to post-hackathon (breadth, not shape)

- Sys-1 **engine**: auto-deriving the descriptor from docs + live MCP/API introspection.
- Multi-component / multi-attack coverage; the attack-family catalog.
- Target-agnostic adapters (the toolkit is currently hardwired to the stand).
- CI/regression export, LLM-judge second opinion.
