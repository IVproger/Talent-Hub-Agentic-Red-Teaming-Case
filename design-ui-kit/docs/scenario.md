# Сценарии и атаки

## Список · `[data-mk-scenarios] > .mk-scenario[data-id]`
Кнопка: bg-card, radius 16, padding 16×18, border 1.5px border. Выбранный (`aria-selected="true"`) — border bg-dark. Внутри: `__title` 14/600 + `__count` моно 11 secondary; `__desc` 12 secondary 1.4; `.mk-tag`. Событие `mk:scenario` с `{id}`.

## Карточка сценария
`.mk-card` gap 20: H2 + мета (id · ATLAS) слева, чип «Оракул» справа → 4 `.mk-param` в grid 4 колонки (атакующий, жертва, режим стенда, сессий — **зависят от сценария, не глобальны**) → `.mk-body` → плашка «Механика» (моно 12/600 через стрелки) → список `.mk-attack-item` → футер с оценкой и кнопками, `margin-top:auto`, border-top.

## `.mk-param`
bg-page radius 12 padding 12×14; `__k` 11 secondary, `__v` моно 13/500.

## `.mk-attack-item`
Grid 32 / 1.4fr / 1fr, gap 14, padding 14×16, radius 14, border 1px. `__n` моно 12 tertiary («01»); `__name` 14/600 + `__how` 13 secondary; `__cfg` моно 12 secondary + `__probe` моно 12 ellipsis.

Сетка экрана: `.mk-grid-2-5` (список | карточка).
