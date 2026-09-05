"""Read-only Mongo snapshots through mongosh, locally or inside Compose."""
from __future__ import annotations

import copy
import json
import os
import subprocess
from uuid import uuid4

from ...errors import PipelineConfigurationError
from ...normalize.projection import dotted
from ..base import CalibrationResult, EvidenceKind, Marker, Observation


class DbQueryProvider:
    kind = EvidenceKind.MEMORY_SNAPSHOT

    def __init__(self, config, runner=subprocess.run, *, environ=None):
        self.config = copy.deepcopy(config)
        self.runner = runner
        self.environ = os.environ if environ is None else environ
        self._marker = Marker(uuid4().hex)
        if config.get("driver", "mongo") != "mongo":
            raise NotImplementedError("db_query: реализован только driver=mongo.")
        for name in ("db", "collection"):
            if not isinstance(config.get(name), str) or not config[name]:
                raise PipelineConfigurationError(f"db_query требует {name}.")

    def mark(self):
        return self._marker

    def read_visible(self, principal, session_id):
        from .visibility import read_target_view
        return read_target_view(self.config, principal, session_id, self.runner)

    def _query(self):
        config = self.config
        env = dict(self.environ)
        connection = "db"
        if config.get("uri_env"):
            uri = self.environ.get(config["uri_env"])
            if not uri:
                raise RuntimeError("Не задана переменная окружения uri_env для Mongo.")
            env["MOROK_MONGO_URI"] = uri
            connection = "new Mongo(process.env.MOROK_MONGO_URI)"
            target = f"{connection}.getDB({json.dumps(config['db'])})"
        else:
            target = f"db.getSiblingDB({json.dumps(config['db'])})"
        script = (f"const target = {target};\n"
                  f"print(JSON.stringify(target.getCollection({json.dumps(config['collection'])})"
                  f".find({json.dumps(config.get('query', {}))}).toArray()));\n")
        command = []
        if config.get("compose_file"):
            command = ["docker", "compose", "-f", config["compose_file"], "exec", "-T"]
            if config.get("uri_env"):
                command += ["-e", "MOROK_MONGO_URI"]
            command += [config.get("service", "mongo")]
        command += [config.get("executable", "mongosh"), "--quiet", "--file", "/dev/stdin"]
        try:
            result = self.runner(command, input=script, env=env, capture_output=True,
                                 text=True, check=True, timeout=config.get("timeout", 30))
            if result.returncode:
                raise ValueError
            raw = result.stdout.strip().splitlines()[-1]
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data[config["collection"]]
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise ValueError
            return data, raw
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
            raise RuntimeError("Не удалось прочитать корректный снимок Mongo.") from None

    def collect(self, since):
        if since != self._marker:
            raise ValueError("Маркер принадлежит другому источнику памяти.")
        documents, raw = self._query()
        payload = {"store_id": self.config.get("store_id", self.config["collection"]),
                   "documents": documents, "record": copy.deepcopy(self.config.get("record", {})),
                   "scope": self.config.get("scope")}
        return [Observation(self.kind, payload, raw)]

    def calibrate(self):
        try:
            documents, _ = self._query()
            if not documents:
                return CalibrationResult(False, "Коллекция доступна, но пуста: привязки полей не подтверждены.")
            declaration = self.config.get("record", {})
            for record in documents:
                content = dotted(record, declaration["content"])
                if content is None or not str(content).strip():
                    raise ValueError
                if declaration.get("key") and dotted(record, declaration["key"]) in (None, ""):
                    raise ValueError
            return CalibrationResult(True, "Поля снимка памяти подтверждены.")
        except (RuntimeError, KeyError, IndexError, TypeError, ValueError):
            return CalibrationResult(False, "Источник памяти недоступен или record-привязка не подтверждена.")
