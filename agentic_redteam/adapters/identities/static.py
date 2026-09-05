"""Resolve role and credential templates without storing secrets in profiles."""
from __future__ import annotations

import copy
import os

from ...errors import PipelineConfigurationError
from ..base import Principal
from .base import Credential


def principal_for(config: dict, role: str) -> Principal:
    try:
        fields = config["roles"][role]
        declaration = config.get("principal", {})
        attribute = declaration.get("attribute")
        if not attribute and len(fields) == 1:
            attribute = next(iter(fields))
        value = fields[attribute]
        if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value):
            raise ValueError
        if declaration.get("type") == "decimal" and not str(value).isascii():
            raise ValueError
        if declaration.get("type") == "decimal" and not str(value).isdecimal():
            raise ValueError
        return Principal(attribute, str(value))
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineConfigurationError("Роль отсутствует или её principal некорректен.") from exc


def render_credential(config: dict, role: str, principal: Principal, secret: str | None = None) -> Credential:
    values = {**config["roles"][role], "role": role, "principal": principal.value}
    if secret is not None:
        values["secret"] = secret
    declaration = config.get("credential", {})
    try:
        def render(section):
            result = {}
            for key, value in declaration.get(section, {}).items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError
                result[key] = value.format_map(values)
            return result
        return Credential(principal, render("headers"), render("body_fields"))
    except (KeyError, ValueError, AttributeError, IndexError, TypeError):
        raise PipelineConfigurationError("Невозможно разрешить шаблон credential; проверьте поля роли и secret_env.") from None


class StaticIdentityProvider:
    def __init__(self, profile_identities: dict, environ=None):
        self.config = copy.deepcopy(profile_identities)
        self.environ = os.environ if environ is None else environ

    def acquire(self, role: str) -> Credential:
        principal = principal_for(self.config, role)
        env_name = self.config.get("credential", {}).get("secret_env")
        secret = self.environ.get(env_name) if env_name else None
        if env_name and not secret:
            raise PipelineConfigurationError("Переменная окружения secret_env не задана.")
        return render_credential(self.config, role, principal, secret)

    def release(self, credential: Credential) -> None:
        """Static credentials remain owned by the operator."""
