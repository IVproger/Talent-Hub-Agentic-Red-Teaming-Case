# MOROK Design Kit · v1

Готовый к подключению набор: CSS-токены, базовые стили, классы компонентов, поведение на чистом JS и по одной демо-странице на компонент.

## Структура

```
design_kit/
  index.html              обзор: цвета, типографика, радиусы, отступы, ссылки на компоненты
  tokens.json             токены в JSON (для Figma Tokens / Style Dictionary / Tailwind)
  css/tokens.css          --mk-* CSS custom properties
  css/base.css            шрифты, сброс, типографика (.mk-h1 …), сетки, анимации
  css/components.css      все компоненты (.mk-btn, .mk-card, .mk-badge …)
  js/components.js        window.MK: steps, tabs, chips, scenarios, sidebarToggle, runSim, init
  assets/                 логотип-глаз (белый / тёмный)
  components/*.html       живые демо каждого компонента
  docs/*.md               спецификация каждого компонента
```

## Подключение

```html
<link rel="stylesheet" href="design_kit/css/tokens.css">
<link rel="stylesheet" href="design_kit/css/base.css">
<link rel="stylesheet" href="design_kit/css/components.css">
<script src="design_kit/js/components.js"></script>
```

`components.js` сам инициализирует всё по data-атрибутам (`data-mk-steps`, `data-mk-tabs`, `data-mk-scenarios`, `data-mk-chip`, `data-mk-toggle-sidebar`). Для динамически вставленного DOM вызвать `MK.init(root)`.

Шрифты грузятся из Google Fonts в `base.css`. Для закрытого контура положить Golos Text и JetBrains Mono локально и заменить `@import` на `@font-face`.

## Принципы

1. Витрина, не пульт: один этап — один экран — одно главное действие.
2. Брендовый красный `--mk-color-brand-red` — только логотип и одна кнопка на экран. Риск — `--mk-color-negative`, это другой красный.
3. Данные — моно (`--mk-font-mono`): идентификаторы, аргументы, вердикты, метрики, лог, мета. Интерфейс — Golos.
4. Контент заполняет высоту: сетка шага `flex:1`, ряд навигации `.mk-page-nav` прижат к низу.
5. Без теней. Иерархия — цветом поверхностей и рамками.

## Компоненты

| Компонент | Демо | Спека |
|---|---|---|
| Каркас приложения | components/app-shell.html | docs/app-shell.md |
| Навигация (шаги, вкладки, сайдбар) | components/navigation.html | docs/navigation.md |
| Кнопки | components/buttons.html | docs/buttons.md |
| Бейджи и статусы | components/badges.html | docs/badges.md |
| Карточки и списки | components/cards-lists.html | docs/cards-lists.md |
| Сценарии и атаки | components/scenario.html | docs/scenario.md |
| Поля ввода | components/forms.html | docs/forms.md |
| Таблицы | components/table.html | docs/table.md |
| Баннеры и итог | components/banners-verdict.html | docs/banners-verdict.md |
| Прогресс и лог | components/progress-log.html | docs/progress-log.md |
| Схема и след | components/architecture-trail.html | docs/architecture-trail.md |

Экраны и поведение целиком — в `../DESIGN.md`. Референс — `../MOROK Demo Flow.html`.
