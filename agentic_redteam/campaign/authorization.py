"""US-34: рамка авторизованного тестирования.

Автономный генератор атак обязан иметь формальное разрешение и окно, в
котором оно действует. Проверка стоит наравне с preflight: нет разрешения —
кампания не стартует, даже на своём стенде. Разрешение попадает в
`campaign.json` и в условия воспроизведения отчёта.

Здесь только кампания: о цели модуль ничего не знает.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

FIELDS = ("authorized_by", "scope", "until")


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Authorization:
    authorized_by: str
    scope: str
    until: str

    def as_record(self) -> dict:
        return {field: getattr(self, field) for field in FIELDS}


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AuthorizationError(
            f"authorization.until должно быть датой ГГГГ-ММ-ДД, получено: {value}"
        ) from exc


def authorization_from_mapping(mapping: dict, today: date | None = None) -> Authorization:
    block = (mapping or {}).get("authorization")
    if not isinstance(block, dict) or not block:
        raise AuthorizationError(
            "Кампания не стартует без блока authorization "
            "(authorized_by, scope, until) в конфигурации."
        )
    missing = [field for field in FIELDS if not str(block.get(field) or "").strip()]
    if missing:
        raise AuthorizationError(
            "В authorization не заполнено: " + ", ".join(missing) + "."
        )
    until = _as_date(block["until"])
    if until < (today or date.today()):
        raise AuthorizationError(
            f"Разрешение на тестирование истекло {until.isoformat()} — обновите authorization."
        )
    return Authorization(
        authorized_by=str(block["authorized_by"]).strip(),
        scope=str(block["scope"]).strip(),
        until=until.isoformat(),
    )
