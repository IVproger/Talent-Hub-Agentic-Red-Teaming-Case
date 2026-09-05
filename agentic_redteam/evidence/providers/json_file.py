"""Read-only JSON memory snapshots for profiles such as DVAA."""
import copy
import json
from pathlib import Path
from uuid import uuid4

from ...normalize.projection import dotted, project_memory
from ..base import CalibrationResult, EvidenceKind, Marker, Observation


class JsonFileProvider:
    kind = EvidenceKind.MEMORY_SNAPSHOT

    def __init__(self, config):
        self.config = copy.deepcopy(config)
        self._marker = Marker(uuid4().hex)

    def mark(self):
        return self._marker

    def collect(self, since):
        if since != self._marker:
            raise ValueError("Некорректный маркер JSON-памяти.")
        try:
            raw = Path(self.config["path"]).read_text(encoding="utf-8")
            documents = json.loads(raw)
            if self.config.get("select"):
                documents = dotted(documents, self.config["select"])
            if not isinstance(documents, list) or any(not isinstance(item, dict) for item in documents):
                raise ValueError
            return [Observation(self.kind, {"store_id": self.config["store_id"], "documents": documents,
                    "record": self.config["record"], "scope": self.config.get("scope")}, raw)]
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError("Не удалось прочитать JSON-снимок памяти.") from None

    def calibrate(self):
        try:
            observations = self.collect(self.mark())
            documents = observations[0].payload["documents"]
            declaration = self.config["record"]
            for document in documents:
                if dotted(document, declaration["content"]) in (None, ""):
                    raise ValueError
                project_memory(document, declaration, self.config.get("scope"))
            return CalibrationResult(bool(documents), "JSON-память доступна." if documents else "JSON-память пуста: привязка не подтверждена.")
        except (RuntimeError, ValueError, KeyError, TypeError):
            return CalibrationResult(False, "JSON-память недоступна или record-привязка неверна.")
