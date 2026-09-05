"""Profile-driven HTTP chat transport and optional memory finalization."""
from __future__ import annotations

import json
import re
import urllib.request
from functools import partial
from urllib.parse import quote

from ..doctor import CheckResult
from ..errors import PipelineConfigurationError
from ..normalize.projection import dotted
from .base import AdapterFeature, TargetUnavailable, UnsupportedFeature


def urllib_post(url, body, headers, *, method="POST", timeout=300):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _render(value, context):
    if isinstance(value, dict):
        return {key: _render(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, context) for item in value]
    if isinstance(value, str):
        try:
            return value.format_map(context)
        except (KeyError, ValueError, IndexError, AttributeError):
            raise PipelineConfigurationError("Некорректный шаблон HTTP-запроса в профиле.") from None
    return value


def _response_at(value, path):
    # The core dotted helper owns mapping access; indexed response segments are
    # a transport concern until the shared projection API supports them.
    for segment in path.split("."):
        match = re.fullmatch(r"([^\[\]]+)((?:\[\d+\])*)", segment)
        if not match:
            raise ValueError("Некорректный путь ответа.")
        value = dotted(value, match[1])
        for index in re.findall(r"\[(\d+)\]", match[2]):
            value = value[int(index)]
    return value


class HttpChatAdapter:
    def __init__(self, profile, identities, transport=None, *, mode_switcher=None):
        profile.validate()
        self.profile = profile
        self.identities = identities
        self.transport = transport or partial(urllib_post, timeout=profile.entrypoint.get("timeout", 300))
        self.mode_switcher = mode_switcher
        self._credentials = {}
        self._mode = None
        self._closed = False
        features = set()
        # Explicit sessions can be carried in a body template or finalize path.
        if "{session}" in json.dumps(profile.entrypoint):
            features.add(AdapterFeature.SESSIONS)
        if "commit_memory" in profile.entrypoint:
            features.add(AdapterFeature.MEMORY_COMMIT)
        for mode in profile.modes.values():
            features.add(AdapterFeature.MODE_PER_REQUEST if mode["scope"] == "per_request"
                         else AdapterFeature.MODE_PER_DEPLOYMENT)
        self.features = frozenset(features)

    @classmethod
    def from_profile(cls, profile, **kwargs):
        from .identities.static import StaticIdentityProvider
        from .identities.docker_exec_mint import DockerExecMintProvider
        providers = {"static": StaticIdentityProvider, "docker-exec-mint": DockerExecMintProvider}
        provider = providers.get(profile.identities.get("provider"))
        if provider is None:
            raise PipelineConfigurationError("Провайдер личностей не поддерживается.")
        return cls(profile, provider(profile.identities), **kwargs)

    def _url(self, path):
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise PipelineConfigurationError("HTTP path должен начинаться с одного '/'.")
        return self.profile.entrypoint["base_url"].rstrip("/") + path

    def _request(self, path, body, headers, method="POST"):
        if self._closed:
            raise TargetUnavailable("Адаптер уже закрыт.")
        url = self._url(path)
        try:
            if method == "POST":
                return self.transport(url, body, headers)
            return self.transport(url, body, headers, method=method)
        except (OSError, ValueError):
            raise TargetUnavailable("Цель недоступна или вернула некорректный HTTP/JSON-ответ.") from None

    def preflight(self):
        declaration = self.profile.entrypoint.get("preflight")
        if not declaration:
            return [CheckResult("target", False, "Не задан entrypoint.preflight.path для read-only проверки.")]
        try:
            self._request(declaration["path"], None, {"Accept": "application/json"}, method="GET")
            return [CheckResult("target", True, "Цель доступна.")]
        except (TargetUnavailable, KeyError, PipelineConfigurationError):
            return [CheckResult("target", False, "Read-only HTTP-проверка цели не прошла.")]

    def open_session(self, role, session_id, mode):
        if self._closed:
            raise TargetUnavailable("Адаптер уже закрыт.")
        if self.profile.modes and mode not in self.profile.modes:
            raise PipelineConfigurationError("Режим отсутствует в профиле.")
        declaration = self.profile.modes.get(mode, {})
        if declaration.get("scope") == "per_deployment" and self._mode != mode:
            if self.mode_switcher is None:
                raise UnsupportedFeature("Для per_deployment необходим mode_switcher.")
            self.mode_switcher(mode, declaration)
            self._mode = mode
        if role not in self._credentials:
            self._credentials[role] = self.identities.acquire(role)
        return HttpChatSession(self, self._credentials[role], session_id, mode)

    def close(self):
        if self._closed:
            return
        self._closed = True
        credentials, self._credentials = self._credentials, {}
        try:
            for credential in credentials.values():
                self.identities.release(credential)
        finally:
            close = getattr(self.transport, "close", None)
            if close:
                close()


class HttpChatSession:
    def __init__(self, adapter, credential, session_id, mode):
        self.adapter = adapter
        self.credential = credential
        self.principal = credential.principal
        self.session_id = session_id
        self.mode = mode

    def _body_headers(self, declaration):
        context = {"session": self.session_id, "mode": self.mode,
                   "principal": self.principal.value}
        body = _render(declaration.get("body", {}), context)
        headers = {"Content-Type": "application/json", **_render(declaration.get("headers", {}), context),
                   **self.credential.headers}
        if not isinstance(body, dict):
            raise PipelineConfigurationError("request.body должен быть словарём.")
        return body, headers

    def send(self, message):
        entrypoint = self.adapter.profile.entrypoint
        extra, headers = self._body_headers(entrypoint.get("request", {}))
        mode = self.adapter.profile.modes.get(self.mode, {})
        body = {"messages": [{"role": "user", "content": message}], **extra}
        if mode.get("scope") == "per_request":
            body.update(_render(mode.get("body", {}), {"mode": self.mode, "session": self.session_id}))
        body.update(self.credential.body_fields)
        data = self.adapter._request(entrypoint.get("chat_path", "/v1/chat/completions"), body, headers)
        try:
            value = _response_at(data, entrypoint["response"]["path"])
            if not isinstance(value, str):
                raise ValueError
            return value
        except (KeyError, IndexError, TypeError, ValueError):
            raise TargetUnavailable("Ответ цели не соответствует entrypoint.response.path.") from None

    def commit_memory(self):
        declaration = self.adapter.profile.entrypoint.get("commit_memory")
        if declaration is None:
            raise UnsupportedFeature("Цель не поддерживает commit_memory.")
        path = _render(declaration["path"], {"session": quote(self.session_id, safe=""), "mode": self.mode})
        body, headers = self._body_headers(declaration.get("request", {}))
        body.update(self.credential.body_fields)
        data = self.adapter._request(path, body, headers, declaration.get("method", "POST"))
        try:
            facts = _response_at(data, declaration["response"]["path"])
            if not isinstance(facts, list) or any(not isinstance(item, dict) for item in facts):
                raise ValueError
            return facts
        except (KeyError, IndexError, TypeError, ValueError):
            raise TargetUnavailable("Ответ commit_memory не соответствует профилю.") from None
