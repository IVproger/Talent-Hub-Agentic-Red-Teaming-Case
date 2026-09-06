# Навигация

## Шапка · `.mk-header`
Высота 60, bg-dark, padding 10×20, gap 16. Три зоны: `__brand` (иконка ☰ 36×36 + `.mk-logo` 44×30 глаз + «MOROK» 17/700 .18em), `__nav` (flex 1 1 380px, центр), `__aside` (`.mk-target-chip`: моно 12, точка статуса). На узких экранах шаги переносятся на вторую строку.

## Шаги · `.mk-steps[data-mk-steps] > .mk-step[data-step]`
Группа: fill-on-dark, radius 22, padding 3, gap 2, flex-wrap. Кнопка: 7×12, 13/500, text-on-dark-secondary; `__n` — кружок 18 моно 11.
- активный `aria-current="step"`: фон #fff, текст bg-dark, кружок rgba(15,25,55,.1)
- пройденный `.mk-step--done`: кружок positive-muted/positive, текст «✓»
- будущий: кружок rgba(214,214,229,.12)
Все шаги кликабельны всегда. JS: `MK.steps(nav)` → `{set(n)}`, событие `mk:step`.

## Вкладки · `.mk-tabs[data-mk-tabs] > .mk-tab[data-tab]`
Группа fill-secondary radius 99 padding 3 gap 2; кнопка 7×16 13/500 secondary; активная `aria-selected="true"` #fff/primary. Панели `[data-tab-panel="id"]` внутри `[data-mk-tabs-scope]` переключаются через `hidden`. Событие `mk:tab`.

## Сайдбар · `.mk-sidebar`
288px, bg-card, border-right, padding 24×20, gap секций 28, scroll. Секции (`.mk-sidebar__section`, заголовок `.mk-label`): **Цель аудита** (плашка: имя 14/600, моно-id 11, статус) → **Подключение** (4 `.mk-kv`; до синхронизации «не проверено») → **Модели** (генератор / целевой агент / автор отчёта) → **История прогонов** (`.mk-history`). Сайдбар универсален — не зависит от выбранного сценария. Сворачивание: `[data-mk-toggle-sidebar]` → `hidden`.
