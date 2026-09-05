# Blueprint — спеки MOROK

Дизайн-спеки системы. Ядро — фундамент; эпики плагинятся в его замороженные
интерфейсы. Статус: **все аспекты бэклога охвачены дизайном** (реализация —
по планам).

## Ядро (фундамент)

| Спек | Что описывает |
|---|---|
| [morok-core-design](2026-09-04-morok-core-design.md) | Профиль, адаптер, evidence+тиры, нормализация/предикаты/вердикт, runner, storage, CLI (§12), миграция |

## Эпики (поверх Ядра)

| Эпик | Спек | US |
|---|---|---|
| E2 карта поверхности | [surface-map](2026-09-05-e2-surface-map-design.md) | US-03/05/06/07 |
| E3/E4 генерация атак | [attack-generation](2026-09-05-e3e4-attack-generation-design.md) | US-08/11/14/21 |
| E5 кампания/UI | [campaign-ui](2026-09-05-e5-campaign-ui-design.md) | US-15/16/18 |
| E6 база знаний | [knowledge-base](2026-09-05-e6-knowledge-base-design.md) | US-19 |
| E7 технический отчёт | [technical-report](2026-09-05-e7-technical-report-design.md) | US-24/25/26 |
| E8 регрессия | [regression](2026-09-05-e8-regression-design.md) | US-28/29 |
| E9 бизнес-отчёт | [business-report](2026-09-05-e9-business-report-design.md) | US-32/33 |
| Сквозное | [crosscutting](2026-09-05-crosscutting-safety-metrics-lifecycle.md) | US-34/35, US-13, US-36 |

## Планы реализации

| План | Охват |
|---|---|
| [morok-core-plan](../plans/2026-09-05-morok-core-plan.md) | Ядро, блоки 0–5 (TDD) |

Планы эпиков пишутся по мере перехода к их реализации (через `writing-plans`).

## Связанное

- Диаграммы: [`../diagrams/`](../diagrams/) (2 overview + 5 детальных)
- Стандарты: [`../references/`](../references/) (OWASP Agentic/LLM Top 10, ATLAS)
- Совместимость стендов: [`../target-compatibility-scan.md`](../target-compatibility-scan.md)
