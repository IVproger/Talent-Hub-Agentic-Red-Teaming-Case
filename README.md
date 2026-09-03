# Agentic Red Teaming — Attack Toolkit

State-based red-team tooling for the **GenAI investment agent memory stand**. Instead of
judging the agent's chat reply, it asserts a compromise against the agent's *state*: a
poisoned cross-user global-policy write, or a tool call issued with another client's `cus`.

> Authorized educational use only. The target (`genai-invest-agent-memory-stand`, bundled as
> a git submodule under `stand/`) is a purpose-built security lab that intentionally ships
> these vulnerabilities. Do not point this tooling at any system you are not authorized to test.

## Scenarios (`agentic_redteam/scenarios/`)

- `bac_tool_argument` — Broken Access Control via tool-argument manipulation.
- `memory_policy_conformant` — cross-user memory poisoning via a global-scoped fact.
- `poison_to_tool_chain` — poisoned memory → cross-client tool call (multi-step).
- `system_prompt_leak` — system-prompt extraction (reconnaissance).

The verdict is decided from the stand's own memory (MongoDB) and the invest-server tool-call
log — never from the agent's reply text. ASR is estimated over N trials per scenario.

## Run

Bring up the stand (bundled submodule), then run the toolkit:

```bash
git submodule update --init            # fetch the stand under stand/
docker compose -f stand/docker-compose.yml up -d --build

python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m agentic_redteam.cli -n 3     # full scenario library, ASR over 3 trials
```

Configuration (endpoint, stand compose file, Mongo collections) lives in
`agentic_redteam/config.py` and is overridable via environment variables.
