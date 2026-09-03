# Runtime architecture

## Supported path

Both the CLI and Streamlit UI call `agentic_redteam.pipeline.run_pipeline`.
Adaptive BAC and bundled YAML scenarios share target preflight, state evidence,
deterministic scoring, report generation, telemetry and per-run storage.

```text
config/target.yaml
        |
        +--> stand sync --> stand/.env --> agent-api
        |
        +--> doctor (read only)
        |
        +--> CLI / UI --> pipeline --> runs/<run-id>/
                                |
                                +--> agent-api --> ReAct/tools/memory
                                |
                                +--> deterministic verdict
```

`config/target.yaml` owns non-secret model/provider settings. `stand/.env` owns
credentials and operational limits. The sync command projects the YAML target
model into the three stand variables required by its current implementation.

## Evidence boundary

The runner captures memory snapshots and the invest-server access log around an
attempt. Scorers consume that state, never the natural-language answer or a
Langfuse trace. This keeps verdicts reproducible when report generation or
telemetry is unavailable.

The access log is currently global to the isolated local stand. Do not mix
unrelated traffic with a run until the stand emits a run/session correlation ID
in its audit events.

## Distributed tracing

When enabled, the runner starts `redteam.run` and injects W3C trace context into
the two target endpoints. The stand only instruments requests with a
`traceparent`, continues the same OpenTelemetry context, and adds observations
for target LLM calls, tools and memory orchestration. Both sides use one
Langfuse project; `component` metadata distinguishes `redteam-runner` from
`target-stand`, while `agent_role` distinguishes `attacker`, `target` and
`report_writer` observations.

All telemetry is optional and fail-open. Capture is redacted and bounded before
export. The local artifact manifest is the correlation record between the trace
and the deterministic run.
