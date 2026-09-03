"""StateTracer — white-box observation of the target agent's internal state.

This is the tool's differentiator: instead of judging the final chat text, we
snapshot the agent's long-term memory (MongoDB) and observe the tool calls it
actually made (invest-server access log, whose path carries the chosen `cus`
argument). A compromise is asserted against this state.
"""
from __future__ import annotations

import json
import re
import subprocess
from contextlib import nullcontext
from typing import Any

from . import config
from .state import MemorySnapshot, ToolCall

_TOOL_RE = re.compile(config.TOOL_CALL_LOG_RE)


class StateTracer:
    def __init__(self, compose_file: str | None = None, telemetry: Any | None = None):
        self.compose_file = compose_file or config.COMPOSE_FILE
        self.telemetry = telemetry

    def _observation(self, name: str, **kwargs):
        if self.telemetry is None:
            return nullcontext(_NullObservation())
        return self.telemetry.observation(name, **kwargs)

    def _compose(self, *args: str) -> list[str]:
        return ["docker", "compose", "-f", self.compose_file, *args]

    def snapshot_memory(self) -> MemorySnapshot:
        """Read all tracked long-term memory collections from MongoDB."""
        with self._observation("evidence.memory.snapshot") as observation:
            colls = list(config.MEMORY_COLLECTIONS)
            script = (
                "var out={};"
                f"{json.dumps(colls)}.forEach(function(c)"
                "{out[c]=db[c].find({},{_id:0}).toArray();});"
                "print(JSON.stringify(out));"
            )
            out = subprocess.run(
                self._compose("exec", "-T", "mongo", "mongosh", config.MONGO_DB, "--quiet", "--eval", script),
                capture_output=True, text=True, check=True,
            )
            data = json.loads(out.stdout.strip().splitlines()[-1])
            observation.update(
                output={name: len(items) for name, items in data.items()}
            )
            return MemorySnapshot(collections=data)

    def reset_memory(self) -> None:
        """Clear long-term + working memory for a clean, reproducible run."""
        with self._observation("evidence.memory.reset") as observation:
            colls = json.dumps(list(config.MEMORY_COLLECTIONS))
            subprocess.run(
                self._compose("exec", "-T", "mongo", "mongosh", config.MONGO_DB, "--quiet", "--eval",
                         f"{colls}.forEach(function(c){{try{{db[c].deleteMany({{}});}}catch(e){{}}}});"),
                capture_output=True, text=True, check=True,
            )
            subprocess.run(self._compose("exec", "-T", "redis", "redis-cli", "FLUSHALL"),
                           capture_output=True, text=True, check=True)
            observation.update(output={"reset": True})

    def log_marker(self) -> int:
        """Current invest-server access-log length; pass to tool_calls_since()."""
        out = subprocess.run(
            self._compose("logs", "--no-color", "invest-server"),
            capture_output=True, text=True, check=True,
        )
        return len(out.stdout.splitlines())

    def tool_calls_since(self, marker: int) -> list[ToolCall]:
        """Client-data tool calls (with their cus argument) since a log marker."""
        with self._observation(
            "evidence.tool_calls", metadata={"source": "invest-server-access-log"}
        ) as observation:
            out = subprocess.run(
                self._compose("logs", "--no-color", "invest-server"),
                capture_output=True, text=True, check=True,
            )
            lines = out.stdout.splitlines()[marker:]
            calls: list[ToolCall] = []
            for line in lines:
                m = _TOOL_RE.search(line)
                if m:
                    calls.append(ToolCall(tool="client_data_access", cus=m.group(1)))
            observation.update(
                output={"calls": [{"tool": call.tool, "cus": call.cus} for call in calls]}
            )
            return calls


class _NullObservation:
    def update(self, **_values) -> None:
        return None
