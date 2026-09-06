# Кнопки · `.mk-btn`

| Класс | Фон | Hover | Текст | Padding | Назначение |
|---|---|---|---|---|---|
| `.mk-btn--brand` | brand-red | brand-red-hover | #fff 14/600 | 13×24 | главное действие шага, **одна на экран** |
| `.mk-btn--dark` | bg-dark | bg-dark-hover | #fff 14/600 | 13×24 | «дальше →» |
| `.mk-btn--secondary` | fill-secondary | fill-secondary-hover | text-primary 14/500 | 13×20 | «← назад», вспомогательные |
| `.mk-btn--small` | модификатор | | 13px | 8×14 | внутри баннеров |
| `.mk-btn--ghost-dashed` | transparent | bg-page | text-secondary 13 | 11×14, radius 12 | «+ Добавить файл» |
| `.mk-icon-btn` | fill-on-dark | fill-on-dark-hover | text-on-dark-secondary | 36×36, radius 10 | иконка в шапке |

Radius 99. Без рамок и теней. Hover без transition. Focus — `--mk-focus`.

## Ряд навигации шага · `.mk-page-nav`

`display:flex; justify-content:space-between; margin-top:auto`. Слева secondary «← …», справа brand или dark «… →». На первом шаге слева подпись (.mk-caption), на последнем — только «← К отчёту».
