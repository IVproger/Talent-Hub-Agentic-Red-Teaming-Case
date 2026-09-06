# Схема архитектуры, след, трейс

## Схема · `.mk-panel > .mk-arch`
Строки `__row` flex-wrap gap 8. `.mk-node`: 9×12, radius 10, моно 12/500, border 1px, bg #fff. `--surface` (поверхность атаки: память, CRM, transfer_funds) attention-muted/attention-border/attention. `--morok` bg-dark/#fff. Точка входа — `.mk-dot--info` внутри узла. Стрелка `__arrow` «→» tertiary. Под схемой легенда 12.

## След находки · `.mk-trail`
Горизонтальная цепочка `__item` (flex 1, min-width 120): `__node` (bg-page radius 12 padding 12×14; `__stage` 11/700 caps secondary; `__detail` моно 11) + `__link` 18×1.5 border-dashed. Точка компрометации — `__node--hit`: negative-muted, border 1.5 negative-bar, stage negative. Этапы: доставка → запись → сохранение → извлечение → действие → эффект.

## Блок трейса
Grid `.mk-grid-1-3`: слева список шагов (строка 10×12 radius 12; выбранная bg-page, точка `.mk-dot--bad`), справа карточка шага: два `.mk-pre` (запрос bg-page; вызов инструмента `--hit` negative-muted с рамкой rgba(255,72,55,.35)) и список проверок (строка border radius 12 padding 10×14: `.mk-badge--pass/--fail`, имя моно 12, evidence 12 secondary).
