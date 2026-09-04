# Диаграммы архитектуры MOROK

Потоки и структура целевого дизайна (см. спек Ядра
`../specs/2026-09-04-morok-core-design.md`).

Каждый файл — **одна** mermaid-диаграмма (Mermaid Live, GitHub и `mmdc`
рендерят по одной за раз; несколько диаграмм в одном файле дают ошибку
парсера).

| Файл | Что показывает | Тип |
|---|---|---|
| `1-structure.mmd` | Общая структура: роли-источники, профиль, ядро, граница цели, отчёты | flowchart TB |
| `2-onboarding.mmd` | Подключение произвольной цели: init → check → verify → гейт покрытия | flowchart TD |
| `3-campaign.mmd` | Прогон кампании: composer → генерация → предпросмотр → runner → evidence → вердикт | sequenceDiagram |
| `4-verdict.mmd` | Вычисление вердикта: proven / indirect / not_proven / error | flowchart TD |
| `5-evidence.mmd` | Нормализация evidence: граница «специфично для цели» ↔ «общее» | flowchart LR |

## Рендер

- GitHub рендерит `.mmd` в превью автоматически.
- Локально: `npx -y @mermaid-js/mermaid-cli -i 1-structure.mmd -o 1-structure.svg`.
- Онлайн: mermaid.live — вставить содержимое одного файла.

Ключевые инварианты, которые диаграммы делают наглядными: в `1-structure`
от ядра нет ни одной прямой стрелки к цели — только через границу; в
`5-evidence` профиль влияет на *перевод* фактов, но не на *предикаты*.
