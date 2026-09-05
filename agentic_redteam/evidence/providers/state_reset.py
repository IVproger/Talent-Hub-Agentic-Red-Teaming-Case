"""Explicit profile-scoped reset; calibration only probes backend health."""
from __future__ import annotations

import copy
import json
import subprocess
from uuid import uuid4

from ...errors import PipelineConfigurationError
from ..base import CalibrationResult, EvidenceKind, Marker


class StateResetProvider:
    kind = EvidenceKind.SESSION_RESET

    def __init__(self, config, runner=subprocess.run):
        self.config = copy.deepcopy(config)
        self.runner = runner
        self._marker = Marker(uuid4().hex)
        if not config.get("compose_file") or not (config.get("mongo") or config.get("redis")):
            raise PipelineConfigurationError("state-reset требует compose_file и декларацию mongo/redis.")
        for backend, field in (("mongo", "collections"), ("redis", "key_patterns")):
            if backend not in config:
                continue
            values = config[backend].get(field)
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v or v == "*" for v in values):
                raise PipelineConfigurationError(f"state-reset требует явный непустой список {backend}.{field}.")
            if not config[backend].get("service"):
                raise PipelineConfigurationError(f"Не задан {backend}.service.")
        if "mongo" in config and not config["mongo"].get("db"):
            raise PipelineConfigurationError("Не задан mongo.db.")

    def _run(self, service, *args, script=None):
        command = ["docker", "compose", "-f", self.config["compose_file"], "exec", "-T", service, *args]
        try:
            result = self.runner(command, input=script, capture_output=True, text=True,
                                 check=True, timeout=self.config.get("timeout", 30))
            if result.returncode:
                raise ValueError
            return result.stdout
        except (OSError, subprocess.SubprocessError, ValueError):
            raise RuntimeError("Операция state-reset не выполнена.") from None

    def mark(self):
        return self._marker

    def collect(self, since):
        if since != self._marker:
            raise ValueError("Некорректный reset-маркер.")
        return []

    def reset(self):
        mongo = self.config.get("mongo")
        if mongo:
            script = (f"const target = db.getSiblingDB({json.dumps(mongo['db'])});\n"
                      f"{json.dumps(mongo['collections'])}.forEach(c => "
                      f"target.getCollection(c).deleteMany({json.dumps(mongo.get('query', {}))}));\n")
            self._run(mongo["service"], "mongosh", "--quiet", "--file", "/dev/stdin", script=script)
        redis = self.config.get("redis")
        if redis:
            options = ["redis-cli", "--raw", "-n", str(redis.get("db", 0))]
            for pattern in redis["key_patterns"]:
                keys = self._run(redis["service"], *options, "--scan", "--pattern", pattern).splitlines()
                for start in range(0, len(keys), 100):
                    self._run(redis["service"], *options, "DEL", *keys[start:start + 100])

    def calibrate(self):
        try:
            mongo = self.config.get("mongo")
            if mongo:
                output = self._run(mongo["service"], "mongosh", "--quiet", "--file", "/dev/stdin",
                    script=f"print(JSON.stringify(db.getSiblingDB({json.dumps(mongo['db'])}).runCommand({{ping:1}})));\n")
                if json.loads(output.strip().splitlines()[-1]).get("ok") != 1:
                    raise ValueError
            redis = self.config.get("redis")
            if redis and self._run(redis["service"], "redis-cli", "--raw", "-n", str(redis.get("db", 0)), "PING").strip() != "PONG":
                raise ValueError
            return CalibrationResult(True, "Backend сброса доступен; состояние не изменялось.")
        except (RuntimeError, ValueError, IndexError, AttributeError):
            return CalibrationResult(False, "Backend сброса недоступен.")
