"""Каталог стандартов как источник идей для генератора AttackBrief.

Описания взяты из зафиксированных источников репозитория
(`docs/blueprint/references/`): OWASP Top 10 for LLM Applications 2026
(`LLM01`–`LLM10`) и OWASP Top 10 for Agentic Applications 2026
(`ASI01`–`ASI10`). Ссылки `ASIxx` относятся к Agentic Top 10, `LLMxx` — к
LLM Top 10. MITRE ATLAS (`AML.Txxxx`) — матрица техник, а не «Top 10»;
репозиторий использует её как систему идентификаторов, поэтому для ATLAS
проверяется формат идентификатора, а не принадлежность фиксированному
списку.

Каталог target-независим: пункты говорят о классах угроз, а не о конкретной
цели. Конкретику добавляет профиль цели при генерации brief.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ATLAS_REF = re.compile(r"AML\.T\d{4}")

STANDARD_SOURCES = {
    "owasp-llm": "OWASP Top 10 for LLM Applications, 2026",
    "owasp-agentic": "OWASP Top 10 for Agentic Applications, 2026",
    "atlas": "MITRE ATLAS (матрица техник)",
}


@dataclass(frozen=True)
class StandardItem:
    ref: str
    source: str
    title: str
    description: str


LLM_ITEMS: tuple[StandardItem, ...] = tuple(
    StandardItem(ref, "owasp-llm", title, description)
    for ref, title, description in (
        ("LLM01", "Prompt Injection",
         "Внедрение инструкций через пользовательский ввод или внешний контент; "
         "эффект доказывается downstream-состоянием, а не текстом ответа."),
        ("LLM02", "Sensitive Information Disclosure",
         "Раскрытие чувствительных данных другим принципалам или наружу."),
        ("LLM03", "Excessive Agency",
         "Агент выполняет действия за пределами заявленных полномочий."),
        ("LLM04", "Supply Chain",
         "Уязвимости в модели, плагинах и зависимостях состава агента."),
        ("LLM05", "Data and Model Poisoning",
         "Отравление обучающих данных или весов (не путать с runtime-памятью)."),
        ("LLM06", "Unbounded Consumption",
         "Неограниченное потребление ресурсов и стоимости."),
        ("LLM07", "Misinformation",
         "Убедительная, но неверная информация от модели."),
        ("LLM08", "Hidden Context Exposure",
         "Утечка системного промпта, чужого или скрытого контекста."),
        ("LLM09", "Vector and Embedding Weaknesses",
         "Кросс-тенантный доступ через векторные хранилища и эмбеддинги."),
        ("LLM10", "Improper Output Handling",
         "Передача вывода модели в downstream-системы без проверки."),
    )
)

AGENTIC_ITEMS: tuple[StandardItem, ...] = tuple(
    StandardItem(ref, "owasp-agentic", title, description)
    for ref, title, description in (
        ("ASI01", "Agent Goal Hijack",
         "Перехват или смещение цели агента; наблюдается по расхождению "
         "действий с заявленной задачей."),
        ("ASI02", "Tool Misuse and Exploitation",
         "Злоупотребление доступными инструментами вне намеренного сценария."),
        ("ASI03", "Identity and Privilege Abuse",
         "Использование идентичности и привилегий агента для доступа к чужим "
         "данным, в том числе через аргументы инструментов."),
        ("ASI04", "Agentic Supply Chain Vulnerabilities",
         "Композиция агента из ненадёжных компонентов и плагинов."),
        ("ASI05", "Unexpected Code Execution",
         "Непреднамеренное выполнение кода в среде агента."),
        ("ASI06", "Memory & Context Poisoning",
         "Отравление долговременной памяти или контекста с эффектом для "
         "других сессий или принципалов."),
        ("ASI07", "Insecure Inter-Agent Communication",
         "Небезопасный обмен между агентами (A2A)."),
        ("ASI08", "Cascading Failures",
         "Каскадные отказы в мультиагентных цепочках."),
        ("ASI09", "Human-Agent Trust Exploitation",
         "Злоупотребление доверием человека к агенту."),
        ("ASI10", "Rogue Agents",
         "Рассогласование целей агента с целями владельца."),
    )
)

# ATLAS — матрица, а не фиксированный список: для brief-ссылок достаточно
# валидного формата идентификатора и указания источника.
ATLAS_ITEM = StandardItem("AML.Txxxx", "atlas", "MITRE ATLAS",
                          "Идентификатор техники из матрицы MITRE ATLAS.")

CATALOG: dict[str, StandardItem] = {item.ref: item for item in LLM_ITEMS}
CATALOG.update({item.ref: item for item in AGENTIC_ITEMS})


def is_valid_ref(ref: object) -> bool:
    if not isinstance(ref, str):
        return False
    return ref in CATALOG or bool(_ATLAS_REF.fullmatch(ref))


def validate_refs(refs: list[str]) -> None:
    invalid = [ref for ref in refs if not is_valid_ref(ref)]
    if invalid:
        raise ValueError(
            "Неизвестные ссылки на стандарты: " + ", ".join(invalid)
            + ". ASIxx — OWASP Agentic Top 10, LLMxx — OWASP LLM Top 10, "
            "AML.Txxxx — MITRE ATLAS."
        )


def standard_items(sources: tuple[str, ...] = ("owasp-llm", "owasp-agentic")) -> list[dict]:
    """Описания выбранных источников как вход генератору brief.

    ATLAS по умолчанию не входит: это уточняющие ссылки, а не источник идей.
    """
    rows: list[dict] = []
    for source in sources:
        if source == "owasp-llm":
            rows.extend(_row(item) for item in LLM_ITEMS)
        elif source == "owasp-agentic":
            rows.extend(_row(item) for item in AGENTIC_ITEMS)
        elif source == "atlas":
            rows.append(_row(ATLAS_ITEM))
        else:
            raise ValueError(f"Неизвестный источник стандартов: {source}")
    return rows


def _row(item: StandardItem) -> dict:
    return {
        "ref": item.ref,
        "source": STANDARD_SOURCES[item.source],
        "title": item.title,
        "description": item.description,
    }
