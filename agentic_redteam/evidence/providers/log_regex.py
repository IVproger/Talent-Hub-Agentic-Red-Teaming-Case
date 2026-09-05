"""Profile-declared log capture with append-only cursor validation."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from ...errors import PipelineConfigurationError
from ...normalize.projection import dotted
from ..base import CalibrationResult, EvidenceKind, Marker, Observation


def _digest(lines):
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


class LogRegexProvider:
    kind = EvidenceKind.TOOL_CALLS

    def __init__(self, config, runner=subprocess.run):
        self.config = copy.deepcopy(config)
        self.runner = runner
        self._id = uuid4().hex
        try:
            self.pattern = re.compile(config["pattern"])
            self.captures = config.get("captures", [])
            if not isinstance(self.captures, list) or len(self.captures) > self.pattern.groups:
                raise ValueError
            if any(not isinstance(name, str) for name in self.captures):
                raise ValueError
            if config["source"]["kind"] not in ("docker-log", "file", "cli-json"):
                raise ValueError
        except (KeyError, TypeError, ValueError, re.error):
            raise PipelineConfigurationError("Некорректный source/pattern/captures для log_regex.") from None

    def _lines(self):
        source = self.config["source"]
        try:
            if source["kind"] == "file":
                return Path(source["path"]).read_text(encoding="utf-8").splitlines()
            if source["kind"] == "docker-log":
                command = ["docker", "compose"]
                compose = source.get("compose_file", self.config.get("compose_file"))
                if compose:
                    command += ["-f", compose]
                command += ["logs", "--no-color", source["service"]]
            else:
                command = source["command"]
                if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
                    raise ValueError
            result = self.runner(command, capture_output=True, text=True, check=True,
                                 timeout=self.config.get("timeout", 30))
            if result.returncode:
                raise ValueError
            if source["kind"] == "docker-log":
                return result.stdout.splitlines()
            items = json.loads(result.stdout)
            if source.get("select"):
                items = dotted(items, source["select"])
            if not isinstance(items, list):
                raise ValueError
            lines = []
            for item in items:
                value = dotted(item, source.get("field", "message")) if isinstance(item, dict) else item
                if not isinstance(value, str):
                    raise ValueError
                lines.append(value)
            return lines
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            raise RuntimeError("Не удалось прочитать источник tool calls.") from None

    def mark(self):
        lines = self._lines()
        return Marker(json.dumps({"source": self._id, "count": len(lines), "digest": _digest(lines)}))

    def _observations(self, lines):
        result = []
        for line in lines:
            for match in self.pattern.finditer(line):
                fields = {**match.groupdict(), **dict(zip(self.captures, match.groups()))}
                try:
                    args = {name: template.format_map(fields) for name, template in self.config.get("args", {}).items()}
                except (KeyError, ValueError, AttributeError):
                    raise RuntimeError("Захваты лога не соответствуют шаблонам args.") from None
                payload = {"tool": fields.get("tool", self.config.get("tool", "tool_call")),
                           "principal": fields.get("principal"), "args": args,
                           "call_context": fields}
                result.append(Observation(self.kind, payload, line))
        return result

    def collect(self, since):
        try:
            marker = json.loads(since.token)
            count = marker["count"]
            if marker["source"] != self._id or not isinstance(count, int) or count < 0:
                raise ValueError
            lines = self._lines()
            if len(lines) < count or _digest(lines[:count]) != marker["digest"]:
                raise RuntimeError("Лог изменён или обрезан после mark; полнота evidence не подтверждена.")
            return self._observations(lines[count:])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise RuntimeError("Некорректный маркер источника tool calls.") from None

    def calibrate(self):
        try:
            observations = self._observations(self._lines())
            expected = self.config.get("calibration", {}).get("expected_principal")
            ok = expected is not None and any(o.payload["principal"] == str(expected) for o in observations)
            return CalibrationResult(ok, "Контрольный principal найден в логе." if ok else
                                     "Контрольный principal не задан или не найден в логе.")
        except RuntimeError:
            return CalibrationResult(False, "Источник tool calls недоступен или привязка не подтверждена.")
