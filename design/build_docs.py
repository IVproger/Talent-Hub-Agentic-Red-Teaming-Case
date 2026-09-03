#!/usr/bin/env python3
"""
Генерация человекочитаемой документации по палитре и типографике
из разобранных токенов. Запускать после parse_tokens.py.

Выход:
  01-brand-foundations/color-palette.md
  01-brand-foundations/typography.md
  05-ui-patterns/swatches.html   — визуальный лист образцов (открыть в браузере)
"""
import json
import os
import re
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
TOK = os.path.join(BASE, "03-design-tokens")

rows = json.load(open(os.path.join(TOK, "tokens-active.json"), encoding="utf-8"))
typo = json.load(open(os.path.join(TOK, "typography-scale.json"), encoding="utf-8"))
by_name = {t["name"]: t for t in rows}


def val(t):
    return t.get("hex") or t.get("resolved") or t["value"]


def pick(pattern, exclude=None):
    sel = [t for t in rows if re.match(pattern, t["name"])]
    if exclude:
        sel = [t for t in sel if not re.search(exclude, t["name"])]
    return sorted(sel, key=lambda t: t["name"])


def table(tokens, show_alpha=True):
    out = ["| Токен | Значение | HEX |", "| --- | --- | --- |"]
    for t in tokens:
        raw = t.get("resolved") or t["value"]
        hexv = t.get("hex", "")
        a = t.get("alpha")
        if show_alpha and a not in (None, 1.0):
            hexv = f"{hexv} · α {a}"
        out.append(f"| `{t['name']}` | `{raw}` | {hexv} |")
    return "\n".join(out)


def scale_rows(prefix, theme):
    """Собирает шкалы вида prefix-<name>-<n> в строки."""
    groups = defaultdict(list)
    pat = re.compile(rf"--color-{theme}-{prefix}-(.+?)-(\d+)$")
    for t in rows:
        m = pat.match(t["name"])
        if m:
            groups[m.group(1)].append((int(m.group(2)), t))
    return {k: [t for _, t in sorted(v)] for k, v in sorted(groups.items())}


# ---------------------------------------------------------------- палитра
md = []
md.append("""# Цветовая палитра Альфа-Банка

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
""")

md.append("## 1. Фирменные константы\n")
md.append("Не зависят от темы. Это ядро айдентики.\n")
md.append(table([t for t in pick(r"--color-static-brand") if t["source"] == "colors-brand.css"]))
md.append("""
`--color-static-brand-red` — тот самый «Альфа-красный» `#EF3124`. Он же зашит
в официальные SVG логотипов (см. `02-logos/`), он же встречается на живом
alfabank.ru как `rgb(239, 49, 36)`. Три независимых источника сходятся.

### Ловушка в именовании

В системе есть ещё три токена с тем же префиксом `--color-static-brand-`:
""")
md.append(table([t for t in pick(r"--color-static-brand") if t["source"] != "colors-brand.css"]))
md.append("""
Они объявлены в файле `colors-x5.css` и принадлежат **ко-бренду X5**, а не
Альфа-Банку. Префикс `brand` здесь вводит в заблуждение. Проверяйте поле
`source` в `tokens.json`, а не только имя токена.

Аналогично устроены `colors-go.css` (суббренд «Go»), `colors-students.css`
и `colors-pfm.css` — это отдельные продуктовые палитры, не общая айдентика.
""")

md.append("\n---\n\n## 2. Акцент\n")
md.append("Основное действие интерфейса. В светлой теме — фирменный красный.\n")
md.append("\n### Светлая тема\n")
md.append(table(pick(r"--color-light-accent")))
md.append("\n### Тёмная тема\n")
md.append(table(pick(r"--color-dark-accent")))
md.append("""
Обратите внимание: в тёмной теме `accent-primary` осветляется до `#f83a2a`.
Чистый `#ef3124` на тёмном фоне даёт недостаточный контраст, поэтому система
сдвигает его, а исходный оттенок уезжает в `-inverted`.
""")

md.append("\n---\n\n## 3. Базовые поверхности\n")
md.append("`base` — фон приложения, `modal` — фон всплывающих слоёв поверх него.\n")
md.append("\n### base, светлая / тёмная\n")
md.append(table(pick(r"--color-light-base")))
md.append("\n")
md.append(table(pick(r"--color-dark-base")))
md.append("\n### modal, светлая / тёмная\n")
md.append(table(pick(r"--color-light-modal")))
md.append("\n")
md.append(table(pick(r"--color-dark-modal")))
md.append("""
Тёмная тема строится на четырёх ступенях: `#121213` → `#1c1c1e` → `#29292c` → `#353539`.
Это не чистый чёрный, а тёплый угольный. Модальные слои всегда на ступень светлее фона.
""")

md.append("\n---\n\n## 4. Текст\n")
md.append("""Токены текста заданы через **альфа-канал**, а не через непрозрачный цвет.
Это позволяет тексту корректно ложиться на любую подложку.
""")
md.append("\n### Светлая тема\n")
md.append(table(pick(r"--color-light-text", exclude=r"(inverted|hover|press)")))
md.append("\n### Тёмная тема\n")
md.append(table(pick(r"--color-dark-text", exclude=r"(inverted|hover|press)")))
md.append("""
Иерархия одинакова в обеих темах: primary → secondary → tertiary → quaternary,
с прозрачностью примерно 0.88 / 0.55 / 0.38 / 0.18. Значение
`rgba(3, 3, 6, 0.88)` — самый частый цвет текста на живом alfabank.ru.
""")

md.append("\n---\n\n## 5. Статусы\n")
md.append("""Четыре смысловых состояния: `positive`, `negative`, `attention`, `info`.
У каждого есть приглушённые заливки `muted` и `muted-alt` для плашек и бейджей.

Для нашего продукта это основной инструмент кодирования степени риска.
""")
md.append("\n### Светлая тема\n")
md.append(table(pick(r"--color-light-status", exclude=r"(inverted|hover|press)")))
md.append("\n### Тёмная тема\n")
md.append(table(pick(r"--color-dark-status", exclude=r"(inverted|hover|press)")))
md.append("""
`negative` (`#ff4837`) намеренно отличается от фирменного `#ef3124`. Красный бренда
и красный ошибки — разные цвета, и смешивать их нельзя: иначе каждая кнопка
начинает читаться как предупреждение.
""")

md.append("\n---\n\n## 6. Нейтральная шкала\n")
md.append("""Сквозная шкала `neutral-0 … neutral-1500` — на неё переехали фоны, границы
и разделители. Внутри есть подгруппа `translucent-*` с альфа-каналом,
она нужна для наложений на цветные подложки.
""")
ncore = [t for t in rows
         if re.match(r"--color-light-neutral-\d+$", t["name"])]
ncore.sort(key=lambda t: int(t["name"].rsplit("-", 1)[1]))
ndark = [t for t in rows if re.match(r"--color-dark-neutral-\d+$", t["name"])]
ndark.sort(key=lambda t: int(t["name"].rsplit("-", 1)[1]))
md.append("\n### Светлая тема, базовые ступени\n")
md.append(table(ncore))
md.append("\n### Тёмная тема, базовые ступени\n")
md.append(table(ndark))

md.append("\n---\n\n## 7. Палитры для графиков\n")
md.append("""Дизайн-система содержит готовые наборы под визуализацию данных.
Для дашборда с метриками атак это снимает вопрос «какие цвета брать для серий».

### Категориальные наборы (qualitative)

Наборы подобраны так, чтобы соседние цвета различались и в дальтонизме,
и в чёрно-белой печати. Берите набор целиком, не смешивая цвета из разных.
""")
qs = scale_rows("qualitative", "light")
md.append("\n| Набор | Кол-во | Цвета |\n| --- | --- | --- |")
for k, v in qs.items():
    md.append(f"| `{k}` | {len(v)} | " + " ".join(t.get("hex", "") for t in v) + " |")
md.append("""
`flexible` из 14 цветов — для случаев, когда число серий заранее неизвестно.
Наборы `duocolor` / `tricolor` / `tetracolor` — для фиксированного числа категорий.

### Последовательные шкалы (sequential)

По 8 ступеней от насыщенного к светлому. Для тепловых карт, градаций плотности
и любой метрики, у которой есть направление «больше — меньше».
""")
ss = scale_rows("sequential", "light")
md.append("\n| Шкала | Ступеней | Цвета (1 → 8) |\n| --- | --- | --- |")
for k, v in ss.items():
    md.append(f"| `{k}` | {len(v)} | " + " ".join(t.get("hex", "") for t in v) + " |")

md.append("\n---\n\n## 8. Тени и радиусы\n")
sh = pick(r"--shadow")
md.append(f"\nТеней в системе: {len(sh)}. Четыре семейства: обычные, `-hard` (плотнее), "
          "`-up` (свет снизу), `-hard-up`. Внутри каждого — шкала `xs / s / m / l / xl`.\n")
md.append("\nТени многослойные: каждая собрана из 2–6 наложенных теней с малой прозрачностью.\n")
md.append("\n```css\n--shadow-xs: 0 4px 8px rgba(0, 0, 0, 0.04), 0 0 1px rgba(0, 0, 0, 0.04);\n```\n")
br = [t for t in pick(r"--border-radius") if re.match(r"--border-radius-\d+$", t["name"])]
br.sort(key=lambda t: int(t["name"].rsplit("-", 1)[1]))
md.append("\n### Радиусы\n")
md.append("\n| Токен | Значение |\n| --- | --- |")
for t in br:
    md.append(f"| `{t['name']}` | {t['value']} |")
md.append("""
Плюс `--border-radius-circle: 50%` и `--border-radius-pill: 99px`.

На живом сайте доминируют `32px` (крупные карточки), `99px` (кнопки-таблетки),
`24px`, `16px`, `8px`. Это заметно круглее типичного корпоративного интерфейса
и является узнаваемой чертой пластики бренда.
""")

os.makedirs(os.path.join(BASE, "01-brand-foundations"), exist_ok=True)
open(os.path.join(BASE, "01-brand-foundations", "color-palette.md"), "w", encoding="utf-8").write("\n".join(md))

# ---------------------------------------------------------------- типографика
t = []
t.append("""# Типографика

Файл сгенерирован `design/build_docs.py` из `03-design-tokens/typography-scale.json`.

## Шрифты

| Роль | Гарнитура | Где взять |
| --- | --- | --- |
| Фирменный шрифт бренда | **Styrene A** (Berton Hasebe) | коммерческая лицензия, [type.today](https://type.today) |
| Интерфейсный шрифт | **Alfa Interface Sans** | проприетарный, публично не распространяется |
| Фолбэк и фактический шрифт веба | системный стек | бесплатно |

Токены гарнитур:

```css
--font-family-system:   system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Helvetica, sans-serif;
--font-family-styrene:  'Styrene UI', <тот же системный стек>;
--font-family-alfasans: 'Alfa Interface Sans', <тот же системный стек>;
```

**Практический вывод для нашего кита.** Публичный alfabank.ru отрисовывается
системным стеком: замеры computed-стилей на живых страницах не показали
ни одного веб-шрифта. Styrene A под лицензией, Alfa Interface Sans не отдаётся
наружу. Значит, в прототипе безопаснее всего взять системный стек, а для
заголовков — близкий по духу бесплатный гротеск. Styrene A ставить только
если заказчик передаст лицензию.

## Шкала

Шесть семейств. Различаются насыщенностью и назначением, размеры внутри
семейств повторяются.

| Семейство | Насыщенность | Назначение |
| --- | --- | --- |
| `key` | 500 | Крупные числа и промо-цифры, 64–144 px |
| `headline` | 500 | Заголовки интерфейса, 20–48 px |
| `promo` | 400 | Заголовки маркетинга, 20–48 px |
| `accent` | 700 | Выделенный текст и подписи компонентов |
| `action` | 500 | Текст интерактивных элементов, кнопок |
| `paragraph` | 400 | Основной текст |
""")

fam = defaultdict(list)
for k in typo:
    fam[k.split("_")[0]].append(k)
for group in ["key", "headline", "promo", "accent", "action", "paragraph"]:
    if group not in fam:
        continue
    t.append(f"\n### {group}\n")
    t.append("| Стиль | Размер | Интерлиньяж | Насыщенность | Трекинг |")
    t.append("| --- | --- | --- | --- | --- |")
    for k in sorted(fam[group]):
        v = typo[k]
        t.append(f"| `{k}` | {v.get('font-size','—')} | {v.get('line-height','—')} | "
                 f"{v.get('font-weight','—')} | {v.get('letter-spacing','—')} |")

t.append("""
## Что реально используется на сайте

Замеры computed-стилей главной страницы и продуктовых разделов:

| Размер / насыщенность / интерлиньяж | Роль |
| --- | --- |
| 16px / 400 / normal | основной текст, самый частый стиль |
| 14px / 400 / 20px | вторичный текст, подписи |
| 14px / 500 / 20px | ссылки и мелкие действия |
| 16px / 500 / 24px | акцентный текст в карточках |
| 22px / 700 / 26px | заголовки блоков |
| 30px / 700 / 36px | заголовок раздела |
| 40px / 700 / 48px | заголовок страницы |

Расхождение с дизайн-системой: продуктовый сайт ставит заголовкам
насыщенность **700**, тогда как токены `headline_*` описывают **500**.
Маркетинговый сайт и приложение живут по разным правилам. Для внутреннего
инструмента корректнее следовать токенам, то есть 500.
""")
open(os.path.join(BASE, "01-brand-foundations", "typography.md"), "w", encoding="utf-8").write("\n".join(t))

print("готово:")
print("  01-brand-foundations/color-palette.md")
print("  01-brand-foundations/typography.md")
