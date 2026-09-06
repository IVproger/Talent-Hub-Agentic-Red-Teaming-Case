# Каркас приложения

```
.mk-app (100vh, column, overflow hidden)
├─ .mk-header (60px, bg-dark)
│   ├─ .mk-header__brand  ☰ + логотип
│   ├─ .mk-header__nav    .mk-steps
│   └─ .mk-header__aside  .mk-target-chip
└─ .mk-body (flex 1, row)
    ├─ .mk-sidebar (288px, scroll)
    └─ .mk-main (flex 1, scroll)
        └─ .mk-content (padding 28 40 40, column, gap 24, flex 1)
            ├─ .mk-page-head  .mk-meta → .mk-h1 → .mk-lead
            ├─ .mk-grid … .mk-grow   основная сетка шага
            └─ .mk-page-nav          ← secondary | primary →
```

Правила:
- Прокручивается только `.mk-main` (и сайдбар при переполнении). Шапка фиксирована.
- Основная сетка шага получает `.mk-grow` (flex 1) и при необходимости `grid-template-rows: 1fr auto`, чтобы карточки заполняли высоту. Textarea внутри — `.mk-grow`.
- `.mk-page-nav` всегда последний ряд, `margin-top:auto`.
- Целевая ширина ≥ 1280. До 1100 сетки схлопываются в одну колонку (`base.css`).

Сетки по шагам: 1 — `mk-grid-1-1` + span-all; 2 — `mk-grid-3-2` + span-all; 3 — `mk-grid-2-5`; 4 — `mk-grid-2-3`; 5 трейс — `mk-grid-1-3`, отчёт — `mk-grid-3-2`; 6 — `mk-grid-1-1`.

Полный пример экрана «Контекст цели» — `components/app-shell.html`.
