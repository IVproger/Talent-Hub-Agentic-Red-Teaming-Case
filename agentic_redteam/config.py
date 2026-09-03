"""Runtime configuration, all overridable via environment variables."""
import os
from pathlib import Path

# The target stand's OpenAI-compatible endpoint.
AGENT_API = os.environ.get("AGENT_API", "http://localhost:8600")

# docker compose file of the target stand — used for white-box state tracing
# (reading mongo/redis and the invest-server access log). This is legitimate for
# the cybersecurity-department use case: the target is deployed locally and owned.
# Defaults to the bundled `stand/` submodule at the repository root.
COMPOSE_FILE = os.environ.get(
    "STAND_COMPOSE_FILE",
    str(Path(__file__).resolve().parents[1] / "stand" / "docker-compose.yml"),
)

MONGO_DB = os.environ.get("MONGO_DB", "agent_memory")

# Long-term memory collections we snapshot. `agent_policy_memories` is the
# cross-user global-policy store (the memory-poisoning sink).
MEMORY_COLLECTIONS = (
    "agent_policy_memories",
    "semantic_memories",
    "episodic_memories",
    "dialog_sessions",
)

# invest-server access-log line marking a real client-data tool access; the
# captured group is the `cus` argument the agent chose for the tool call.
TOOL_CALL_LOG_RE = r'"(?:GET|POST) /clients/(\d+)'

REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "300"))
