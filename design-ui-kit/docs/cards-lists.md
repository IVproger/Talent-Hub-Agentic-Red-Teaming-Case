# Карточки и списки

## `.mk-card`
bg-card, radius 20, padding 24, column flex gap 16. `.mk-card__head` — заголовок (.mk-h3) и мета (.mk-meta) по краям, baseline. `--dark` — bg-dark, для лога. `--flush` — без padding, overflow hidden (итог отчёта).

## `.mk-panel`
Вторичная плашка внутри карточки: bg-page, radius 16, padding 18. `--row` — radius 12, padding 12×14.

## `.mk-file-row`
bg-page, radius 12, padding 11×14, gap 12, align flex-start. `__kind` моно 11/600 secondary ширина 40; далее столбик `__name` 13/500 (переносится, не обрезать) + `__meta` 12 secondary.

## `.mk-attack-row`
padding 12×14, radius 12. `__n` моно 12 tertiary 18px; `__name` 13/500 flex:1 ellipsis; справа `.mk-badge`. Фон: `--proven` negative-muted; `--not-proven`/`--running` bg-page; PENDING прозрачный.

## `.mk-kv`
Строка ключ–значение сайдбара: padding 8×0, border-bottom, 13px. `__k` secondary, `__v` моно 12 с точкой 6px.

## `.mk-history`
Кнопка-карточка истории: radius 12, border, padding 10×12; id моно 11 secondary, имя 12, ASR моно 600 negative. Hover bg-page.
