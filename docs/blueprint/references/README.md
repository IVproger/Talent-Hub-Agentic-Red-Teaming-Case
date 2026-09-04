# Blueprint — внешние ссылки

Источники-стандарты для слоя шаблонов атак (эпик E3) и генерации (E4).
Каждый шаблон цитирует конкретный пункт; отсутствие точного соответствия
помечается явно (US-08 AC4).

| Стандарт | Тип | Файл | Первоисточник |
|---|---|---|---|
| OWASP Top 10 for Agentic Applications 2026 | ASI01–ASI10, агентный | [owasp-agentic-top10-2026.md](owasp-agentic-top10-2026.md) | <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/> |
| OWASP Top 10 for LLM Applications 2026 | LLM01–LLM10, model/app | [owasp-llm-top10-2026.md](owasp-llm-top10-2026.md) | <https://github.com/GenAI-Security-Project/GenAI-LLM-Top10> |
| MITRE ATLAS | матрица техник `AML.Txxxx` | (в обоих файлах) | <https://atlas.mitre.org/> |

## Статус решения

Основа каталога шаблонов E3 (агентный vs LLM vs сочетание) — **не
зафиксирована**, обсуждается. Наблюдение из карт вердикта: агентный список
(ASI03=BAC, ASI06=memory poisoning) ложится на state-based модель точнее;
LLM-список полезен для общих рисков, но три пункта (LLM04/05/06) вне области.
