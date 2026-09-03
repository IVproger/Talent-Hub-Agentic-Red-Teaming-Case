# Цветовая палитра Альфа-Банка

Источник значений: пакет `@alfalab/core-components-vars` из открытой дизайн-системы
Core Components ([github.com/core-ds/core-components](https://github.com/core-ds/core-components)),
директория `packages/vars/src`. Все значения ниже извлечены автоматически
скриптом `design/parse_tokens.py`, а не переписаны глазами.

Файл сгенерирован `design/build_docs.py`. Не редактировать вручную — правки затрутся.

## Как устроены токены

Система именует токены по схеме `--color-<тема>-<роль>-<вариант>`:

* `--color-light-*` и `--color-dark-*` объявлены **в одном файле** и задают
  светлую и тёмную темы. Переключение темы делается подключением файла
  `colors-*-dark.css`, который переопределяет `--color-light-X: var(--color-dark-X)`.
  То есть в коде вы всегда ссылаетесь на `light`-имена, а тема подменяет значения.
* `--color-static-*` не зависят от темы. Это фирменные константы и служебные шкалы.
* Суффикс `-inverted` — версия цвета для размещения на контрастной подложке.
* Суффиксы `-hover` и `-press` — состояния интерактивных элементов.

### Важно: слой `bg / graphic / border / specialbg` устарел

В актуальной версии темы целиком помечены `deprecated` группы
`--color-*-bg-*`, `--color-*-graphic-*`, `--color-*-border-*`, `--color-*-specialbg-*`
(всего 195 токенов только в светлой теме). Их роль перенесена на сквозные шкалы
`neutral-*` и `status-*`. Для нового продукта берите `neutral` и `status`,
а устаревшие имена используйте только при интеграции со старым кодом.

---

## 1. Фирменные константы

Не зависят от темы. Это ядро айдентики.

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-static-brand-black` | `#000` | #000000 |
| `--color-static-brand-blue` | `#0056ff` | #0056ff |
| `--color-static-brand-bright-blue` | `#00e8f0` | #00e8f0 |
| `--color-static-brand-green` | `#31e300` | #31e300 |
| `--color-static-brand-red` | `#ef3124` | #ef3124 |
| `--color-static-brand-violet` | `#6a4dff` | #6a4dff |
| `--color-static-brand-warm-green` | `#a8f000` | #a8f000 |
| `--color-static-brand-white` | `#fff` | #ffffff |

`--color-static-brand-red` — тот самый «Альфа-красный» `#EF3124`. Он же зашит
в официальные SVG логотипов (см. `02-logos/`), он же встречается на живом
alfabank.ru как `rgb(239, 49, 36)`. Три независимых источника сходятся.

### Ловушка в именовании

В системе есть ещё три токена с тем же префиксом `--color-static-brand-`:

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-static-brand-orange` | `#f76100` | #f76100 |
| `--color-static-brand-primary` | `#5faf2d` | #5faf2d |
| `--color-static-brand-secondary` | `#00afff` | #00afff |

Они объявлены в файле `colors-x5.css` и принадлежат **ко-бренду X5**, а не
Альфа-Банку. Префикс `brand` здесь вводит в заблуждение. Проверяйте поле
`source` в `tokens.json`, а не только имя токена.

Аналогично устроены `colors-go.css` (суббренд «Go»), `colors-students.css`
и `colors-pfm.css` — это отдельные продуктовые палитры, не общая айдентика.


---

## 2. Акцент

Основное действие интерфейса. В светлой теме — фирменный красный.


### Светлая тема

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-light-accent-primary` | `#ef3124` | #ef3124 |
| `--color-light-accent-primary-hover` | `#e32a17` | #e32a17 |
| `--color-light-accent-primary-inverted` | `#f83a2a` | #f83a2a |
| `--color-light-accent-primary-inverted-hover` | `#ff503e` | #ff503e |
| `--color-light-accent-primary-inverted-press` | `#fd624e` | #fd624e |
| `--color-light-accent-primary-press` | `#d72505` | #d72505 |
| `--color-light-accent-secondary` | `#212124` | #212124 |
| `--color-light-accent-secondary-hover` | `#2f2f32` | #2f2f32 |
| `--color-light-accent-secondary-inverted` | `#f2f3f5` | #f2f3f5 |
| `--color-light-accent-secondary-inverted-hover` | `#dcdde1` | #dcdde1 |
| `--color-light-accent-secondary-inverted-press` | `#d2d3d9` | #d2d3d9 |
| `--color-light-accent-secondary-press` | `#353539` | #353539 |

### Тёмная тема

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-dark-accent-primary` | `#f83a2a` | #f83a2a |
| `--color-dark-accent-primary-hover` | `#ff503e` | #ff503e |
| `--color-dark-accent-primary-inverted` | `#ef3124` | #ef3124 |
| `--color-dark-accent-primary-inverted-hover` | `#e32a17` | #e32a17 |
| `--color-dark-accent-primary-inverted-press` | `#d72505` | #d72505 |
| `--color-dark-accent-primary-press` | `#fd624e` | #fd624e |
| `--color-dark-accent-secondary` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-accent-secondary-hover` | `#dcdde1` | #dcdde1 |
| `--color-dark-accent-secondary-inverted` | `#212124` | #212124 |
| `--color-dark-accent-secondary-inverted-hover` | `#2f2f32` | #2f2f32 |
| `--color-dark-accent-secondary-inverted-press` | `#353539` | #353539 |
| `--color-dark-accent-secondary-press` | `#d2d3d9` | #d2d3d9 |

Обратите внимание: в тёмной теме `accent-primary` осветляется до `#f83a2a`.
Чистый `#ef3124` на тёмном фоне даёт недостаточный контраст, поэтому система
сдвигает его, а исходный оттенок уезжает в `-inverted`.


---

## 3. Базовые поверхности

`base` — фон приложения, `modal` — фон всплывающих слоёв поверх него.


### base, светлая / тёмная

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-light-base-bg-alt-primary` | `#f2f3f5` | #f2f3f5 |
| `--color-light-base-bg-alt-primary-inverted` | `#121213` | #121213 |
| `--color-light-base-bg-alt-secondary` | `#fff` | #ffffff |
| `--color-light-base-bg-alt-secondary-inverted` | `#1c1c1e` | #1c1c1e |
| `--color-light-base-bg-alt-tertiary` | `#f2f3f5` | #f2f3f5 |
| `--color-light-base-bg-alt-tertiary-inverted` | `#29292c` | #29292c |
| `--color-light-base-bg-primary` | `#fff` | #ffffff |
| `--color-light-base-bg-primary-inverted` | `#121213` | #121213 |
| `--color-light-base-bg-secondary` | `#f2f3f5` | #f2f3f5 |
| `--color-light-base-bg-secondary-inverted` | `#1c1c1e` | #1c1c1e |
| `--color-light-base-bg-tertiary` | `#fff` | #ffffff |
| `--color-light-base-bg-tertiary-inverted` | `#29292c` | #29292c |


| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-dark-base-bg-alt-primary` | `#121213` | #121213 |
| `--color-dark-base-bg-alt-primary-inverted` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-base-bg-alt-secondary` | `#1c1c1e` | #1c1c1e |
| `--color-dark-base-bg-alt-secondary-inverted` | `#fff` | #ffffff |
| `--color-dark-base-bg-alt-tertiary` | `#29292c` | #29292c |
| `--color-dark-base-bg-alt-tertiary-inverted` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-base-bg-primary` | `#121213` | #121213 |
| `--color-dark-base-bg-primary-inverted` | `#fff` | #ffffff |
| `--color-dark-base-bg-secondary` | `#1c1c1e` | #1c1c1e |
| `--color-dark-base-bg-secondary-inverted` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-base-bg-tertiary` | `#29292c` | #29292c |
| `--color-dark-base-bg-tertiary-inverted` | `#fff` | #ffffff |

### modal, светлая / тёмная

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-light-modal-bg-alt-primary` | `#f2f3f5` | #f2f3f5 |
| `--color-light-modal-bg-alt-primary-inverted` | `#1c1c1e` | #1c1c1e |
| `--color-light-modal-bg-alt-secondary` | `#fff` | #ffffff |
| `--color-light-modal-bg-alt-secondary-inverted` | `#29292c` | #29292c |
| `--color-light-modal-bg-alt-tertiary` | `#f2f3f5` | #f2f3f5 |
| `--color-light-modal-bg-alt-tertiary-inverted` | `#353539` | #353539 |
| `--color-light-modal-bg-primary` | `#fff` | #ffffff |
| `--color-light-modal-bg-primary-inverted` | `#1c1c1e` | #1c1c1e |
| `--color-light-modal-bg-secondary` | `#f2f3f5` | #f2f3f5 |
| `--color-light-modal-bg-secondary-inverted` | `#29292c` | #29292c |
| `--color-light-modal-bg-tertiary` | `#fff` | #ffffff |
| `--color-light-modal-bg-tertiary-inverted` | `#353539` | #353539 |


| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-dark-modal-bg-alt-primary` | `#1c1c1e` | #1c1c1e |
| `--color-dark-modal-bg-alt-primary-inverted` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-modal-bg-alt-secondary` | `#29292c` | #29292c |
| `--color-dark-modal-bg-alt-secondary-inverted` | `#fff` | #ffffff |
| `--color-dark-modal-bg-alt-tertiary` | `#353539` | #353539 |
| `--color-dark-modal-bg-alt-tertiary-inverted` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-modal-bg-primary` | `#1c1c1e` | #1c1c1e |
| `--color-dark-modal-bg-primary-inverted` | `#fff` | #ffffff |
| `--color-dark-modal-bg-secondary` | `#29292c` | #29292c |
| `--color-dark-modal-bg-secondary-inverted` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-modal-bg-tertiary` | `#353539` | #353539 |
| `--color-dark-modal-bg-tertiary-inverted` | `#fff` | #ffffff |

Тёмная тема строится на четырёх ступенях: `#121213` → `#1c1c1e` → `#29292c` → `#353539`.
Это не чистый чёрный, а тёплый угольный. Модальные слои всегда на ступень светлее фона.


---

## 4. Текст

Токены текста заданы через **альфа-канал**, а не через непрозрачный цвет.
Это позволяет тексту корректно ложиться на любую подложку.


### Светлая тема

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-light-text-attention` | `#ea8313` | #ea8313 |
| `--color-light-text-info` | `#2a77ef` | #2a77ef |
| `--color-light-text-negative` | `#ec2d20` | #ec2d20 |
| `--color-light-text-positive` | `#0d9336` | #0d9336 |
| `--color-light-text-primary` | `rgba(3, 3, 6, 0.88)` | #030306 · α 0.88 |
| `--color-light-text-quaternary` | `rgba(5, 11, 44, 0.18)` | #050b2c · α 0.18 |
| `--color-light-text-secondary` | `rgba(4, 4, 19, 0.55)` | #040413 · α 0.55 |
| `--color-light-text-tertiary` | `rgba(5, 8, 29, 0.38)` | #05081d · α 0.38 |

### Тёмная тема

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-dark-text-attention` | `#fa9313` | #fa9313 |
| `--color-dark-text-info` | `#4a9dfc` | #4a9dfc |
| `--color-dark-text-negative` | `#ff4837` | #ff4837 |
| `--color-dark-text-positive` | `#0cc44d` | #0cc44d |
| `--color-dark-text-primary` | `rgba(255, 255, 255, 0.94)` | #ffffff · α 0.94 |
| `--color-dark-text-quaternary` | `rgba(231, 231, 248, 0.18)` | #e7e7f8 · α 0.18 |
| `--color-dark-text-secondary` | `rgba(238, 238, 251, 0.55)` | #eeeefb · α 0.55 |
| `--color-dark-text-tertiary` | `rgba(233, 233, 250, 0.37)` | #e9e9fa · α 0.37 |

Иерархия одинакова в обеих темах: primary → secondary → tertiary → quaternary,
с прозрачностью примерно 0.88 / 0.55 / 0.38 / 0.18. Значение
`rgba(3, 3, 6, 0.88)` — самый частый цвет текста на живом alfabank.ru.


---

## 5. Статусы

Четыре смысловых состояния: `positive`, `negative`, `attention`, `info`.
У каждого есть приглушённые заливки `muted` и `muted-alt` для плашек и бейджей.

Для нашего продукта это основной инструмент кодирования степени риска.


### Светлая тема

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-light-status-attention` | `#fa9313` | #fa9313 |
| `--color-light-status-info` | `#2288fa` | #2288fa |
| `--color-light-status-muted-alt-attention` | `#fde6c8` | #fde6c8 |
| `--color-light-status-muted-alt-info` | `#d8eaff` | #d8eaff |
| `--color-light-status-muted-alt-negative` | `#ffdfdf` | #ffdfdf |
| `--color-light-status-muted-alt-positive` | `#d1f1d7` | #d1f1d7 |
| `--color-light-status-muted-attention` | `#ffefd9` | #ffefd9 |
| `--color-light-status-muted-info` | `#e4f0ff` | #e4f0ff |
| `--color-light-status-muted-negative` | `#ffebeb` | #ffebeb |
| `--color-light-status-muted-positive` | `#dff8e5` | #dff8e5 |
| `--color-light-status-negative` | `#ff4837` | #ff4837 |
| `--color-light-status-positive` | `#0cc44d` | #0cc44d |

### Тёмная тема

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-dark-status-attention` | `#fda136` | #fda136 |
| `--color-dark-status-info` | `#3193fc` | #3193fc |
| `--color-dark-status-muted-alt-attention` | `#412f22` | #412f22 |
| `--color-dark-status-muted-alt-info` | `#293044` | #293044 |
| `--color-dark-status-muted-alt-negative` | `#442926` | #442926 |
| `--color-dark-status-muted-alt-positive` | `#253528` | #253528 |
| `--color-dark-status-muted-attention` | `#36291f` | #36291f |
| `--color-dark-status-muted-info` | `#222a3e` | #222a3e |
| `--color-dark-status-muted-negative` | `#392523` | #392523 |
| `--color-dark-status-muted-positive` | `#232d25` | #232d25 |
| `--color-dark-status-negative` | `#ff4837` | #ff4837 |
| `--color-dark-status-positive` | `#17d055` | #17d055 |

`negative` (`#ff4837`) намеренно отличается от фирменного `#ef3124`. Красный бренда
и красный ошибки — разные цвета, и смешивать их нельзя: иначе каждая кнопка
начинает читаться как предупреждение.


---

## 6. Нейтральная шкала

Сквозная шкала `neutral-0 … neutral-1500` — на неё переехали фоны, границы
и разделители. Внутри есть подгруппа `translucent-*` с альфа-каналом,
она нужна для наложений на цветные подложки.


### Светлая тема, базовые ступени

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-light-neutral-0` | `#fff` | #ffffff |
| `--color-light-neutral-100` | `#f2f3f5` | #f2f3f5 |
| `--color-light-neutral-200` | `#edeef0` | #edeef0 |
| `--color-light-neutral-300` | `#e7e8eb` | #e7e8eb |
| `--color-light-neutral-400` | `#d2d3d9` | #d2d3d9 |
| `--color-light-neutral-500` | `#babbc2` | #babbc2 |
| `--color-light-neutral-700` | `#898991` | #898991 |
| `--color-light-neutral-1300` | `#212124` | #212124 |
| `--color-light-neutral-1500` | `#121213` | #121213 |

### Тёмная тема, базовые ступени

| Токен | Значение | HEX |
| --- | --- | --- |
| `--color-dark-neutral-0` | `#262629` | #262629 |
| `--color-dark-neutral-100` | `#1c1c1e` | #1c1c1e |
| `--color-dark-neutral-200` | `#212124` | #212124 |
| `--color-dark-neutral-300` | `#29292c` | #29292c |
| `--color-dark-neutral-400` | `#353539` | #353539 |
| `--color-dark-neutral-500` | `#4a4a51` | #4a4a51 |
| `--color-dark-neutral-700` | `#898991` | #898991 |
| `--color-dark-neutral-1300` | `#f2f3f5` | #f2f3f5 |
| `--color-dark-neutral-1500` | `#fff` | #ffffff |

---

## 7. Палитры для графиков

Дизайн-система содержит готовые наборы под визуализацию данных.
Для дашборда с метриками атак это снимает вопрос «какие цвета брать для серий».

### Категориальные наборы (qualitative)

Наборы подобраны так, чтобы соседние цвета различались и в дальтонизме,
и в чёрно-белой печати. Берите набор целиком, не смешивая цвета из разных.


| Набор | Кол-во | Цвета |
| --- | --- | --- |
| `duocolor-set-a` | 2 | #0cc44d #ff4837 |
| `duocolor-set-b` | 2 | #0cc44d #fda136 |
| `duocolor-set-c` | 2 | #5388e0 #fda136 |
| `duocolor-set-d` | 2 | #9cc350 #8376e3 |
| `duocolor-set-e` | 2 | #139c99 #fda136 |
| `duocolor-set-f` | 2 | #f6d53d #8376e3 |
| `duocolor-set-g` | 2 | #9cc350 #ba63d6 |
| `flexible` | 14 | #9cc350 #4d75d0 #ec5742 #228c68 #f29b3e #aa52c1 #f8789e #358d43 #4ac5c7 #7b64d3 #5abd69 #2482a2 #f6d53d #da55b4 |
| `tetracolor-set-a` | 4 | #2482a2 #40ba93 #aa52c1 #f6d53d |
| `tetracolor-set-b` | 4 | #7b64d3 #40ba93 #2482a2 #fda136 |
| `tetracolor-set-c` | 4 | #aa52c1 #40ba93 #f6d53d #ff4837 |
| `tricolor-set-a` | 3 | #9cc350 #8376e3 #f6d53d |
| `tricolor-set-b` | 3 | #40ba93 #ba63d6 #fda136 |
| `tricolor-set-c` | 3 | #ff4837 #139c99 #fda136 |
| `tricolor-set-d` | 3 | #9cc350 #5388e0 #ff4837 |
| `tricolor-set-e` | 3 | #fda136 #5388e0 #f6d53d |

`flexible` из 14 цветов — для случаев, когда число серий заранее неизвестно.
Наборы `duocolor` / `tricolor` / `tetracolor` — для фиксированного числа категорий.

### Последовательные шкалы (sequential)

По 8 ступеней от насыщенного к светлому. Для тепловых карт, градаций плотности
и любой метрики, у которой есть направление «больше — меньше».


| Шкала | Ступеней | Цвета (1 → 8) |
| --- | --- | --- |
| `blue` | 8 | #4d75d0 #5388e0 #71a5f2 #82b5f6 #abceff #c0dbff #d6e6fe #e5f0fe |
| `cyan` | 8 | #2482a2 #3492b9 #51b1d7 #5ebee1 #8ad4f3 #a9e1f6 #c7ebfa #def5ff |
| `fuchsia` | 8 | #c648a0 #da55b4 #f278ca #f68ed3 #fdb1e4 #fdc7f1 #ffdafa #ffe9fc |
| `green` | 8 | #358d43 #3b9e4d #5abd69 #6aca7a #8ee29c #a8ecb5 #c2f3cc #dafae2 |
| `indigo` | 8 | #7b64d3 #8376e3 #9b95f2 #a7a7f7 #bfc4fe #ccd5ff #e1e4ff #eeedff |
| `jungle` | 8 | #228c68 #2a9d74 #40ba93 #53c9a4 #7de1c0 #9becd3 #b8f3e2 #d5fbee |
| `magenta` | 8 | #cf4773 #e35583 #f8789e #fc8fb0 #fcb2c6 #ffc9dc #ffdce5 #ffeaee |
| `orange` | 8 | #c97126 #db8127 #f29b3e #f6a850 #fdc17a #fdd39a #ffe3bc #ffefd9 |
| `pistachio` | 8 | #66881f #739823 #8eb43c #9cc350 #b6db76 #c7e793 #d7f0b1 #e5f9ce |
| `purple` | 8 | #aa52c1 #ba63d6 #d086ec #d899f0 #e5bcfa #e9cdfd #f1dfff #faebff |
| `red` | 8 | #db4933 #ec5742 #fe7961 #fc8e7b #fcb1a7 #ffc8c4 #ffdad9 #ffebeb |
| `teal` | 8 | #158886 #139c99 #37b9bb #4ac5c7 #75dddf #98e9e9 #b9f1f3 #d6f8f9 |

---

## 8. Тени и радиусы


Теней в системе: 20. Четыре семейства: обычные, `-hard` (плотнее), `-up` (свет снизу), `-hard-up`. Внутри каждого — шкала `xs / s / m / l / xl`.


Тени многослойные: каждая собрана из 2–6 наложенных теней с малой прозрачностью.


```css
--shadow-xs: 0 4px 8px rgba(0, 0, 0, 0.04), 0 0 1px rgba(0, 0, 0, 0.04);
```


### Радиусы


| Токен | Значение |
| --- | --- |
| `--border-radius-0` | 0 |
| `--border-radius-2` | 2px |
| `--border-radius-4` | 4px |
| `--border-radius-6` | 6px |
| `--border-radius-8` | 8px |
| `--border-radius-10` | 10px |
| `--border-radius-12` | 12px |
| `--border-radius-14` | 14px |
| `--border-radius-16` | 16px |
| `--border-radius-20` | 20px |
| `--border-radius-24` | 24px |
| `--border-radius-32` | 32px |
| `--border-radius-36` | 36px |
| `--border-radius-64` | 64px |

Плюс `--border-radius-circle: 50%` и `--border-radius-pill: 99px`.

На живом сайте доминируют `32px` (крупные карточки), `99px` (кнопки-таблетки),
`24px`, `16px`, `8px`. Это заметно круглее типичного корпоративного интерфейса
и является узнаваемой чертой пластики бренда.
