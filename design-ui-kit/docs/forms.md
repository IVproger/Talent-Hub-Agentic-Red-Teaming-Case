# Поля ввода

## `.mk-field` → `__label` + control
Label 12 secondary, gap 6.

## `.mk-input`, `.mk-textarea`
Border 1px border, radius 12, bg #fff, text-primary. Input padding 11×14, 13px; textarea 12×14, 14/1.55, resize vertical. `--mono` для технических значений (URL, идентификаторы, mermaid). Focus — `--mk-focus`.

## `.mk-dropzone`
Border 1.5px dashed border-dashed, radius 16, bg-page, padding 22, центр: заголовок 14/500 + подпись 12. `--filled` — горизонтальная строка (padding 18, gap 14) с `__icon` 40×40 #fff radius 12 моно 11/600 positive, именем моно 14/500, метой 12 и «✓» positive справа.

## Чипы · `.mk-chip[data-mk-chip][aria-pressed]`
8×14, radius 99, 13/500, border 1.5px border-chip, bg #fff. Нажат — bg-dark фон и рамка, текст #fff. JS `MK.chips(scope)` переключает aria-pressed.

Сетка полей «Точки входа»: 2 колонки, gap 12×16.
