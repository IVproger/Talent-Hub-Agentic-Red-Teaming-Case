# Local Langfuse

This optional stack runs Langfuse on `http://localhost:3001`. It is independent
from the target stand and is not required for verdicts or local artifacts.

1. Copy `.env.example` to `.env` and replace every placeholder. Generate random
   values with `openssl rand -hex 32`; `LANGFUSE_ENCRYPTION_KEY` must be 64 hex
   characters.
2. Start the stack:

   ```bash
   docker compose --env-file deploy/langfuse/.env \
     -f deploy/langfuse/docker-compose.yml up -d
   ```

3. Export the same `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in the runner
   shell. Put the same keys in `stand/.env`; the stand uses
   `LANGFUSE_BASE_URL=http://host.docker.internal:3001`.
4. Recreate only the target API after adding its credentials:

   ```bash
   docker compose -f stand/docker-compose.yml up -d --no-deps --force-recreate agent-api
   ```

The runner creates the root trace and sends W3C trace context to the target.
The target continues it only for red-team requests that contain `traceparent`.
If Langfuse is unavailable, the run and state-based verdict still complete; the
failure is stored as an observability warning.

## Live verification

Run one small campaign after both services have the same project keys:

```bash
python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --scenario bac-tool-argument \
  --mode vulnerable,protected --trials 1 --json
```

Read `trace_id` and `root_observation_id` from the new
`runs/<run-id>/observability.json`. In Langfuse v4, query the resulting tree
without exposing credentials in command history:

```bash
curl --fail --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "http://localhost:3001/api/public/v2/observations?traceId=<trace-id>&limit=100"
```

The same `traceId` must be present on runner observations (`redteam.run`,
`campaign.attempt`) and target observations (`stand.chat`, `stand.react.loop`,
`stand.tool.*`). Target observations must be descendants of
`campaign.attempt`; equal IDs without the parent relationship are not enough to
prove propagation. A completed example from 2026-09-05 is documented in
[`live-langfuse-validation-2026-09-05.md`](../../docs/blueprint/plans/live-langfuse-validation-2026-09-05.md).
