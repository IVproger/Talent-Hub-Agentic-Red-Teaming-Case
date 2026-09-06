# Прогресс и лог прогона

## Карточка прогресса
Строка статуса: `.mk-spinner` 14px (rgba(15,25,55,.15), top bg-dark, spin .9s) + текст 15/600; справа счётчик `.mk-meta` 13 nowrap «N / M атак · P%». `.mk-progress` 6px bg-page, `__fill` bg-dark, transition width .5s. Ниже 4 счётчика 13 secondary с моно-значениями (Доказано — negative).

Тексты статуса: «Ожидание» → «Атакуем · собираем состояние» → «Все атаки выполнены, оракул вынес вердикты».

## Лог · `.mk-card--dark > .mk-log`
Единственная тёмная поверхность контента. min-height 380. Строка `__line`: `__t` время on-dark-tertiary + `__msg`:
- probe — text-on-dark
- вызов агента — `--agent` on-dark-secondary
- PROVEN — `--proven` log-negative
- NOT PROVEN — `--not-proven` log-positive
`__cursor` 8×14 pulse во время работы. Хранить последние ~9 строк. В idle — строка «ожидание запуска · лог появится после старта сценария».

## Симуляция · `MK.runSim(opts)`
`{rows, verdicts[], progress, counter, log, cursor, interval=650, onDone}`. Три фазы на атаку: RUNNING+probe → agent → вердикт; обновляет бейджи строк, фон строк, прогресс, счётчик, лог. Возвращает `{stop}`. Для реального бэкенда заменить на подписку на события прогона с теми же DOM-операциями.

Сетка экрана: `.mk-grid-2-3` (атаки | лог), `align-items:stretch`.
