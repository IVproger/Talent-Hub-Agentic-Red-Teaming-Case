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
