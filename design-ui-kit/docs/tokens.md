# Токены

Файлы: `css/tokens.css` (CSS custom properties), `tokens.json` (машиночитаемо). Источник палитры — Альфа-Банк light.

## Цвета

| Токен | Значение | Применение |
|---|---|---|
| `--mk-color-bg-page` | `#f2f3f5` | фон приложения, вторичные плашки |
| `--mk-color-bg-card` | `#ffffff` | карточки, сайдбар |
| `--mk-color-bg-dark` | `#121213` | шапка, лог, primary-dark |
| `--mk-color-bg-dark-hover` | `#29292c` | hover тёмной кнопки |
| `--mk-color-border` | `rgba(15,25,55,.1)` | разделители, рамки полей |
| `--mk-color-border-soft` | `rgba(15,25,55,.06)` | разделители строк таблиц |
| `--mk-color-border-dashed` | `rgba(15,25,55,.2)` | drop-зоны |
| `--mk-color-border-chip` | `rgba(15,25,55,.15)` | невыбранный чип |
| `--mk-color-fill-secondary` | `rgba(38,55,88,.06)` | secondary-кнопки, группы вкладок |
| `--mk-color-fill-secondary-hover` | `rgba(15,25,55,.1)` | hover secondary |
| `--mk-color-fill-on-dark` | `rgba(214,214,229,.07)` | плашки в шапке |
| `--mk-color-fill-on-dark-hover` | `rgba(222,222,238,.13)` | hover в шапке |
| `--mk-color-text-primary` | `rgba(3,3,6,.88)` | основной текст |
| `--mk-color-text-body` | `rgba(3,3,6,.75)` | абзацы |
| `--mk-color-text-secondary` | `rgba(4,4,19,.55)` | подписи, мета |
| `--mk-color-text-tertiary` | `rgba(5,8,29,.38)` | заголовки секций, номера |
| `--mk-color-text-on-dark` | `rgba(255,255,255,.94)` | основной на тёмном |
| `--mk-color-text-on-dark-secondary` | `rgba(238,238,251,.7)` | вторичный на тёмном |
| `--mk-color-text-on-dark-tertiary` | `rgba(238,238,251,.4)` | время в логе |
| `--mk-color-brand-red` | `#ef3124` | логотип, главная кнопка шага |
| `--mk-color-brand-red-hover` | `#e32a17` | hover главной кнопки |
| `--mk-color-negative` | `#ec2d20` | PROVEN, FAIL, критично |
| `--mk-color-negative-muted` | `#ffebeb` | фон negative |
| `--mk-color-negative-bar` | `#ff4837` | полоса критичности, ASR |
| `--mk-color-attention` | `#ea8313` | высокий, память |
| `--mk-color-attention-muted` | `#ffefd9` | фон attention |
| `--mk-color-attention-border` | `#fa9313` | рамка узлов-поверхностей атаки |
| `--mk-color-positive` | `#0d9336` | PASS, подключён, отражено |
| `--mk-color-positive-dot` | `#0cc44d` | индикатор подключения |
| `--mk-color-positive-muted` | `#dff8e5` | фон positive |
| `--mk-color-info` | `#2288fa` | точки входа, MCP, RUNNING |
| `--mk-color-info-muted` | `#e4f0ff` | фон info |
| `--mk-color-log-negative` | `#ff8d79` | PROVEN в логе |
| `--mk-color-log-positive` | `#4ae777` | NOT PROVEN в логе |

## Радиусы

- `--mk-radius-pill` = 99px
- `--mk-radius-card` = 20px
- `--mk-radius-panel` = 16px
- `--mk-radius-row` = 12px
- `--mk-radius-node` = 10px

## Отступы

- `--mk-space-1` = 4px
- `--mk-space-2` = 8px
- `--mk-space-3` = 12px
- `--mk-space-4` = 16px
- `--mk-space-5` = 20px
- `--mk-space-6` = 24px
- `--mk-space-7` = 28px
- `--mk-space-8` = 40px

Правила: padding карточки 24; gap между карточками 24; между строками списка 8; между элементами в строке 12; между блоками внутри карточки 14–16; контент 28px 40px 40px.

## Шрифты и размеры

- `--mk-font-ui` Golos Text 400/500/600/700
- `--mk-font-mono` JetBrains Mono 400/500/600

- `--mk-size-h1` = 28px
- `--mk-size-h2` = 22px
- `--mk-size-h3` = 16px
- `--mk-size-lead` = 15px
- `--mk-size-body` = 14px
- `--mk-size-row` = 13px
- `--mk-size-caption` = 12px
- `--mk-size-label` = 11px
- `--mk-size-metric` = 22px
- `--mk-size-hero` = 28px

## Раскладка

- `--mk-header-h` = 60px
- `--mk-sidebar-w` = 288px
- `--mk-content-pad-y` = 28px
- `--mk-content-pad-x` = 40px
- `--mk-min-w` = 1280px

## Прочее

- `--mk-focus` — 0 0 0 2px rgba(15,25,55,.25), применяется как box-shadow на :focus
- `--mk-transition` — .5s ease (прогресс-бар)
- Тени не используются.
