# OWASP Top 10 for LLM Applications — 2026

Источник: <https://github.com/GenAI-Security-Project/GenAI-LLM-Top10>
Версия: **2026** (опубликована 4 августа 2026). Вход для слоя шаблонов (E3).

## Список

| ID | Пункт |
|----|-------|
| LLM01:2026 | Prompt Injection |
| LLM02:2026 | Sensitive Information Disclosure |
| LLM03:2026 | Excessive Agency |
| LLM04:2026 | Supply Chain |
| LLM05:2026 | Data and Model Poisoning |
| LLM06:2026 | Unbounded Consumption |
| LLM07:2026 | Misinformation |
| LLM08:2026 | Hidden Context Exposure |
| LLM09:2026 | Vector and Embedding Weaknesses |
| LLM10:2026 | Improper Output Handling |

## Карта на модель вердикта MOROK

Не «покрыли 10 пунктов», а какие из них доказуемы **состоянием** (см. спек
Ядра §5.5). Отчёт о покрытии обязан помечать исключённое явно (US-08 AC4).

| ID | Как ложится | Потолок вердикта |
|----|-------------|------------------|
| LLM01 | канал доставки, не эффект; успех — по downstream-состоянию | по эффекту |
| LLM02 | `isolation_violation` / `tool_principal_mismatch` / canary | **proven** (STATE) |
| LLM03 | наблюдённые tool calls против заявленного набора | **proven** (STATE) |
| LLM04 | провенанс модели/плагинов — не runtime-атака на агента | вне области |
| LLM05 | отравление обучающих данных/весов — НЕ наша runtime-память | вне области |
| LLM06 | DoS/стоимость — не state-verdict, активно DoS-ить нельзя | вне области |
| LLM07 | оценка по тексту ответа | **indirect** (TEXT) |
| LLM08 | утечка системного/чужого контекста; STATE в памяти, TEXT в ответе | proven / indirect |
| LLM09 | кросс-тенант retrieval из вектор-стора → `isolation_violation` | **proven** (STATE) |
| LLM10 | инъекция в downstream → `external_callback` / вредный аргумент | proven / indirect |

## Ловушка LLM05 ≠ memory poisoning

Флагманский класс кейса — **memory poisoning** (runtime-запись в долгую
память с межсессионным/межпользовательским эффектом) — это **НЕ** LLM05.
LLM05 про обучающие данные и веса модели. Наша память ближе к LLM01
(инъекция-канал) + LLM08 (скрытый контекст) + пункту «memory poisoning» из
**агентного** OWASP Top 10. Каждый шаблон цитирует `LLM##:2026` точно;
натягивать memory poisoning на LLM05 нельзя.

## Открытое решение

Основа каталога шаблонов (E3): LLM Top 10 2026 vs OWASP Agentic Top 10 vs
их сочетание — **не зафиксировано**, обсуждается. См. также ATLAS-техники
как систему идентификаторов (у ATLAS нет официального «Top 10»).
