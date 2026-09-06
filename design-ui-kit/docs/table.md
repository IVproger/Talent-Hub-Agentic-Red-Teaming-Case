# Таблицы · `.mk-table`

CSS grid (не `<table>`), gap колонок 14–16. `__th` 11/700 caps .08em tertiary, padding 12 0 10, border-bottom border. `__td` padding 13×0, border-bottom border-soft, 13px. Без зебры и hover.

## Находки
Колонки: `64px | minmax(200px,1.6fr) | 110px | 120px | minmax(220px,1.6fr) | 130px` — ID, Атака, Критичность, Вердикт, Evidence, ATLAS. Min-width 900, обёртка `.mk-table-wrap` со скроллом; карточка padding 8 24 20.
- `__td--id` моно secondary с полосой 3px слева, вынесенной за край (margin-left −13, padding-left 10): `.is-critical` negative-bar, `.is-high` attention-border, иначе прозрачная.
- Атака 13/500. Критичность — `.mk-sev`. `__td--verdict` моно 12/600 secondary, `.is-proven` negative. Evidence `__td--mono` 12 body. ATLAS моно 12 secondary.

## Компоненты (шаг 2)
Колонки `minmax(160px,1.3fr) | minmax(120px,1fr) | minmax(140px,1.4fr) | minmax(90px,.7fr)`, th padding 8×0, td 11×0. Имя моно 500, тип secondary, статус `.mk-status--ok`.
