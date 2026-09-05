"""Temporary HTTP witness for token-bearing callbacks."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from ...errors import PipelineConfigurationError
from ..base import CalibrationResult, EvidenceKind, Marker, Observation


class HttpCanaryProvider:
    kind = EvidenceKind.EXTERNAL_CALLBACK

    def __init__(self, config):
        try:
            host, port = config.get("bind", "127.0.0.1:0").rsplit(":", 1)
            self._capacity = int(config.get("max_events", 10000))
            if self._capacity < 1:
                raise ValueError
            address = (host, int(port))
        except (AttributeError, ValueError):
            raise PipelineConfigurationError("http-canary требует bind=host:port и положительный max_events.") from None
        self._id = uuid4().hex
        self._events = []
        self._lock = threading.Lock()
        self._overflow = False
        self._closed = False
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if len(self.path) > 8192:
                    self.send_error(414)
                    return
                token = parse_qs(urlsplit(self.path).query).get("token", [None])[0]
                status = 204
                if token:
                    with provider._lock:
                        if len(provider._events) >= provider._capacity:
                            provider._overflow = True
                            status = 503
                        else:
                            source = self.client_address[0]
                            raw = json.dumps({"method": self.command, "path": self.path, "source": source})
                            provider._events.append(Observation(provider.kind, {"token": token, "source": source}, raw))
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_args):
                pass

        self._server = ThreadingHTTPServer(address, Handler)
        self._server.daemon_threads = True
        host, port = self._server.server_address
        self.bind_addr = f"http://{host}:{port}"
        self._advertise_url = config.get("advertise_url", self.bind_addr).rstrip("/")
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()

    def url_for(self, token):
        return self._advertise_url + "/?" + urlencode({"token": token})

    def _ensure_live(self):
        if self._closed or not self._thread.is_alive() or self._overflow:
            raise RuntimeError("Canary недоступен или переполнен; полнота evidence не подтверждена.")

    def mark(self):
        with self._lock:
            self._ensure_live()
            return Marker(json.dumps({"source": self._id, "count": len(self._events)}))

    def collect(self, since):
        with self._lock:
            self._ensure_live()
            try:
                marker = json.loads(since.token)
                count = marker["count"]
                if marker["source"] != self._id or type(count) is not int or not 0 <= count <= len(self._events):
                    raise ValueError
            except (AttributeError, TypeError, KeyError, ValueError):
                raise ValueError("Некорректный маркер canary.") from None
            return list(self._events[count:])

    def calibrate(self):
        try:
            self._ensure_live()
            return CalibrationResult(True, "Canary-listener доступен.")
        except RuntimeError:
            return CalibrationResult(False, "Canary-listener недоступен или переполнен.")

    def close(self):
        if not self._closed:
            self._closed = True
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=2)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
