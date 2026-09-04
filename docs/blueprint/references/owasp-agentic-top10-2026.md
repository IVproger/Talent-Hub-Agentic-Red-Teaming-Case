# OWASP Top 10 for Agentic Applications — 2026

Источник: <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/>
Инициатива: <https://genai.owasp.org/initiatives/agentic-security-initiative/>
Версия: **2026** (опубликована 9 декабря 2025). Идентификаторы **ASI01–ASI10**.

> Отдельный ресурс OWASP GenAI Security Project — **не** то же, что
> [OWASP Top 10 for LLM Applications](owasp-llm-top10-2026.md). Целиком про
> автономных агентов, поэтому наши ключевые классы (BAC, memory poisoning)
> ложатся на него напрямую, а не натягиваются.

## Список и карта на модель вердикта MOROK

| ID | Пункт | Как ложится | Потолок |
|----|-------|-------------|---------|
| ASI01 | Agent Goal Hijack | tool-call дивергенция от задачи; «почему» требует reasoning-trace (OTel) | proven / indirect |
| ASI02 | Tool Misuse and Exploitation | tool calls vs разрешённый набор + chaining → canary | **proven** (STATE) |
| **ASI03** | **Identity and Privilege Abuse** | **наш tool-argument BAC / `isolation_violation`** | **proven** (STATE) |
| ASI04 | Agentic Supply Chain Vulnerabilities | runtime-композиция плагинов; провенанс — вне области | частично |
| ASI05 | Unexpected Code Execution (RCE) | наблюдаемо по внешнему эффекту; осторожно по scope | proven / indirect |
| **ASI06** | **Memory & Context Poisoning** | **наш флагман: `memory_write{cross_user}` + `cross_session_effect`** | **proven** (STATE) |
| ASI07 | Insecure Inter-Agent Communication | нужен A2A-канал; нет у нашего стенда → `NOT_APPLICABLE` (есть у DVAA) | зависит от цели |
| ASI08 | Cascading Failures | мульти-агентный blast radius; для одиночного агента вне области | вне области |
| ASI09 | Human-Agent Trust Exploitation | социо/UX — текстовый уровень | **indirect** (TEXT) |
| ASI10 | Rogue Agents | рассогласование целей — по состоянию чисто не доказать | indirect / вне |

## Почему это основной кандидат в основу каталога (E3)

- **ASI03 = наш BAC**, **ASI06 = наш memory poisoning** — прямое соответствие,
  без натягивания (в LLM-списке их пришлось бы вешать на LLM02 / LLM01+LLM08).
- Подсвечивает недостающие источники: ASI01 требует наблюдения за
  **планировщиком** (OTel-спаны ReAct), ASI07/08 — за **межагентным каналом**
  (A2A). См. пробелы источников в скане стендов.

## ATLAS

MITRE ATLAS — не «Top 10», а матрица (16 тактик / 84 техники, v5.1.0). Мы
используем её как систему **идентификаторов техник** (`AML.Txxxx`) в шаблонах,
а не как рейтинг. Отсутствие точного соответствия помечается явно (US-08 AC4).
