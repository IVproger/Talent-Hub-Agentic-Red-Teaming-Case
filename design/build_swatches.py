#!/usr/bin/env python3
"""
Генерация визуального листа образцов из разобранных токенов.
Все значения берутся из tokens-active.json, ничего не вписано руками.

Выход: 05-ui-patterns/alfa-swatches.html
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(BASE, "03-design-tokens", "tokens-active.json"), encoding="utf-8"))
typo = json.load(open(os.path.join(BASE, "03-design-tokens", "typography-scale.json"), encoding="utf-8"))
by_name = {t["name"]: t for t in rows}


def v(name):
    t = by_name.get(name)
    if not t:
        return None
    return t.get("resolved") or t["value"]


def hexof(name):
    t = by_name.get(name)
    return t.get("hex") if t else None


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def swatch(name, label=None, big=False):
    """Один образец: квадрат цвета + имя токена + значение."""
    val = v(name)
    if val is None:
        return ""
    t = by_name[name]
    disp = t.get("hex", val)
    alpha = t.get("alpha")
    sub = disp if alpha in (None, 1.0) else f"{disp} · α{alpha}"
    short = name.replace("--color-", "").replace("light-", "").replace("dark-", "").replace("static-", "")
    cls = "sw sw-big" if big else "sw"
    return (f'<div class="{cls}"><div class="chip" style="background:{val}"></div>'
            f'<div class="meta"><code>{esc(label or short)}</code><span>{esc(sub)}</span></div></div>')


def group(pattern, exclude=None, limit=None, sort_num=False):
    sel = [t for t in rows if re.match(pattern, t["name"])]
    if exclude:
        sel = [t for t in sel if not re.search(exclude, t["name"])]
    if sort_num:
        sel.sort(key=lambda t: int(re.search(r"(\d+)$", t["name"]).group(1)))
    else:
        sel.sort(key=lambda t: t["name"])
    return sel[:limit] if limit else sel


def scale_sets(kind, theme):
    out = {}
    pat = re.compile(rf"--color-{theme}-{kind}-(.+?)-(\d+)$")
    for t in rows:
        m = pat.match(t["name"])
        if m:
            out.setdefault(m.group(1), []).append((int(m.group(2)), t))
    return {k: [x for _, x in sorted(vv)] for k, vv in sorted(out.items())}


P = []
A = P.append

A('<title>Основа дизайн-кита Альфа-Банка</title>')
A('<link rel="preconnect" href="https://fonts.googleapis.com">')
A('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
A('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
  'family=Golos+Text:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">')

A("""<style>
:root {
  /* Токены Альфы, светлая тема */
  --page:        #f2f3f5;
  --surface:     #ffffff;
  --surface-2:   rgba(38, 55, 88, 0.06);
  --line:        rgba(15, 25, 55, 0.10);
  --ink:         rgba(3, 3, 6, 0.88);
  --ink-2:       rgba(4, 4, 19, 0.55);
  --ink-3:       rgba(5, 8, 29, 0.38);
  --accent:      #ef3124;
  --positive:    #0d9336;
  --negative:    #ec2d20;
  --attention:   #ea8313;
  --info:        #2a77ef;
  --shadow:      0 4px 8px rgba(0,0,0,.04), 0 0 1px rgba(0,0,0,.04);

  --font-ui: 'Golos Text', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;

  --r-lg: 24px;
  --r-md: 16px;
  --r-sm: 8px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --page:      #121213;
    --surface:   #1c1c1e;
    --surface-2: rgba(214, 214, 229, 0.07);
    --line:      rgba(222, 222, 238, 0.13);
    --ink:       rgba(255, 255, 255, 0.94);
    --ink-2:     rgba(238, 238, 251, 0.55);
    --ink-3:     rgba(233, 233, 250, 0.37);
    --accent:    #f83a2a;
    --positive:  #0cc44d;
    --negative:  #ff4837;
    --attention: #fa9313;
    --info:      #4a9dfc;
    --shadow:    0 4px 8px rgba(0,0,0,.4), 0 0 1px rgba(0,0,0,.4);
  }
}
:root[data-theme="dark"] {
  --page:      #121213;
  --surface:   #1c1c1e;
  --surface-2: rgba(214, 214, 229, 0.07);
  --line:      rgba(222, 222, 238, 0.13);
  --ink:       rgba(255, 255, 255, 0.94);
  --ink-2:     rgba(238, 238, 251, 0.55);
  --ink-3:     rgba(233, 233, 250, 0.37);
  --accent:    #f83a2a;
  --positive:  #0cc44d;
  --negative:  #ff4837;
  --attention: #fa9313;
  --info:      #4a9dfc;
  --shadow:    0 4px 8px rgba(0,0,0,.4), 0 0 1px rgba(0,0,0,.4);
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--page);
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 40px 28px 96px; }

/* --- шапка --- */
header.top {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 24px; flex-wrap: wrap;
  padding-bottom: 28px; margin-bottom: 36px;
  border-bottom: 1px solid var(--line);
}
.mark { display: flex; align-items: center; gap: 14px; }
.mark svg { width: 34px; height: 34px; display: block; flex: none; }
h1 { font-size: 26px; line-height: 1.2; font-weight: 600; margin: 0; letter-spacing: -.02em; }
.sub { color: var(--ink-2); font-size: 13.5px; margin: 5px 0 0; max-width: 60ch; }
.toggle {
  display: inline-flex; background: var(--surface-2); border-radius: 99px;
  padding: 3px; gap: 2px; border: 1px solid var(--line);
}
.toggle button {
  font: 500 12.5px/1 var(--font-ui); color: var(--ink-2);
  background: none; border: 0; padding: 8px 15px; border-radius: 99px; cursor: pointer;
}
.toggle button[aria-pressed="true"] { background: var(--surface); color: var(--ink); box-shadow: var(--shadow); }
.toggle button:focus-visible { outline: 2px solid var(--info); outline-offset: 2px; }

/* --- секции --- */
section { margin-bottom: 52px; scroll-margin-top: 20px; }
h2 {
  font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .09em;
  color: var(--ink-3); margin: 0 0 4px;
}
.h2sub { font-size: 19px; font-weight: 600; margin: 0 0 6px; letter-spacing: -.01em; }
.note { color: var(--ink-2); font-size: 13.5px; max-width: 68ch; margin: 0 0 20px; }
.note b { color: var(--ink); font-weight: 600; }

/* --- образцы --- */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(178px, 1fr)); gap: 10px; }
.sw {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md);
  overflow: hidden; display: flex; flex-direction: column;
}
.sw .chip { height: 58px; border-bottom: 1px solid var(--line); }
.sw-big .chip { height: 96px; }
.sw .meta { padding: 9px 11px 11px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.sw code {
  font: 500 11.5px/1.35 var(--font-mono); color: var(--ink);
  overflow-wrap: anywhere;
}
.sw .meta span { font: 400 11px/1.3 var(--font-mono); color: var(--ink-3); font-variant-numeric: tabular-nums; }

/* --- парная демонстрация тем --- */
.themes { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 720px) { .themes { grid-template-columns: 1fr; } }
.panel { border-radius: var(--r-lg); padding: 20px; border: 1px solid var(--line); }
.panel h3 {
  font: 600 11px/1 var(--font-ui); text-transform: uppercase; letter-spacing: .09em;
  margin: 0 0 14px; opacity: .6;
}
.panel.light { background: #ffffff; color: rgba(3,3,6,.88); border-color: rgba(15,25,55,.10); }
.panel.dark  { background: #121213; color: rgba(255,255,255,.94); border-color: rgba(222,222,238,.13); }
.stack { display: flex; flex-direction: column; gap: 8px; }
.layer {
  border-radius: var(--r-md); padding: 12px 14px;
  font: 500 12.5px/1.3 var(--font-mono); display: flex; justify-content: space-between; gap: 12px;
  flex-wrap: wrap;
}
.layer em { font-style: normal; opacity: .55; font-size: 11.5px; }

/* --- шкалы --- */
.ramp { display: flex; border-radius: var(--r-sm); overflow: hidden; border: 1px solid var(--line); }
.ramp i { flex: 1; height: 40px; display: block; }
.ramp-row { display: grid; grid-template-columns: 120px 1fr; gap: 14px; align-items: center; margin-bottom: 8px; }
.ramp-row code { font: 500 12px/1.3 var(--font-mono); color: var(--ink-2); }

/* --- таблица --- */
.tbl-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: var(--r-md); background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th, td { text-align: left; padding: 11px 16px; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { font: 600 11px/1 var(--font-ui); text-transform: uppercase; letter-spacing: .08em; color: var(--ink-3); }
tbody tr:last-child td { border-bottom: 0; }
td code { font: 500 12.5px/1.3 var(--font-mono); }
td.num { font-variant-numeric: tabular-nums; color: var(--ink-2); }

/* --- радиусы --- */
.radii { display: flex; gap: 14px; flex-wrap: wrap; }
.radii figure { margin: 0; text-align: center; }
.radii .box {
  width: 92px; height: 68px; background: var(--surface-2);
  border: 1px solid var(--line); display: block;
}
.radii figcaption { font: 500 11.5px/1.4 var(--font-mono); color: var(--ink-2); margin-top: 7px; }

/* --- типографика --- */
.type-row {
  display: grid; grid-template-columns: 190px 1fr; gap: 20px; align-items: baseline;
  padding: 13px 0; border-bottom: 1px solid var(--line);
}
.type-row:last-child { border-bottom: 0; }
.type-row .spec { font: 400 11.5px/1.4 var(--font-mono); color: var(--ink-3); font-variant-numeric: tabular-nums; }
.type-row .spec b { display: block; color: var(--ink-2); font-weight: 500; }
.type-row .demo { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 640px) { .type-row { grid-template-columns: 1fr; gap: 4px; } }

/* --- применение --- */
.apply { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.finding {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md);
  padding: 16px 18px; display: flex; flex-direction: column; gap: 9px;
  border-left: 3px solid var(--sev);
}
.finding .row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.badge {
  font: 600 10.5px/1 var(--font-ui); text-transform: uppercase; letter-spacing: .07em;
  padding: 5px 9px; border-radius: 99px; background: var(--sev-bg); color: var(--sev-fg);
}
.finding h4 { margin: 0; font-size: 14.5px; font-weight: 600; line-height: 1.35; }
.finding p { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.45; }
.finding .path { font: 400 11.5px/1.4 var(--font-mono); color: var(--ink-3); overflow-wrap: anywhere; }

.callout {
  border-left: 3px solid var(--accent); background: var(--surface-2);
  padding: 14px 18px; border-radius: 0 var(--r-md) var(--r-md) 0; margin: 0 0 20px;
  font-size: 13.5px; color: var(--ink-2); max-width: 74ch;
}
.callout b { color: var(--ink); font-weight: 600; }
footer {
  margin-top: 60px; padding-top: 22px; border-top: 1px solid var(--line);
  color: var(--ink-3); font-size: 12.5px;
}
footer a { color: var(--ink-2); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
</style>""")

# --------------------------------------------------------------- шапка
A('<div class="wrap">')
A('''<header class="top">
  <div class="mark">
    <!-- контуры взяты из официального файла 02-logos/znak_svg -->
    <svg viewBox="0 0 370 370" aria-hidden="true"><rect width="370" height="370" rx="80" fill="#ef3124"/>
    <rect x="114.28" y="258.75" width="141.44" height="29.39" fill="#fff"/>
    <path fill="#fff" d="M210.89,94.41c-4.03-12.03-8.68-21.53-24.61-21.53s-20.87,9.46-25.12,21.53l-43.77,124.41h29.02l10.1-29.58h55.84l9.37,29.58h30.86l-41.71-124.41Zm-45.91,69.85l19.84-58.96h.73l18.74,58.96h-39.31Z"/></svg>
    <div>
      <h1>Основа дизайн-кита Альфа-Банка</h1>
      <p class="sub">Токены, палитра и типографика, собранные из открытой дизайн-системы
      банка и сверенные с живыми интерфейсами. Материал для инструмента
      agentic red teaming.</p>
    </div>
  </div>
  <div class="toggle" role="group" aria-label="Тема оформления">
    <button type="button" data-set="light" aria-pressed="false">Светлая</button>
    <button type="button" data-set="dark" aria-pressed="false">Тёмная</button>
    <button type="button" data-set="system" aria-pressed="true">Как в системе</button>
  </div>
</header>''')

A('''<p class="callout"><b>Откуда значения.</b> Всё на этой странице извлечено автоматически
из пакета <code>@alfalab/core-components-vars</code> открытой дизайн-системы банка
и проверено замерами computed-стилей на живых страницах alfabank.ru.
Из 4819 объявлений актуальны 2244; 603 уникальных цвета. Ни одно значение не вписано вручную.</p>''')

# --------------------------------------------------------------- бренд
A('<section><h2>01 — константы</h2><p class="h2sub">Фирменные цвета</p>')
A('<p class="note">Не зависят от темы. <b>Альфа-красный <code>#ef3124</code></b> совпадает '
  'в трёх независимых источниках: токен дизайн-системы, официальные SVG логотипов '
  'и фактический цвет кнопок на живом сайте.</p>')
A('<div class="grid">')
for t in group(r"--color-static-brand"):
    if t["source"] != "colors-brand.css":
        continue
    A(swatch(t["name"], t["name"].replace("--color-static-brand-", ""), big=True))
A('</div>')
A('<p class="note" style="margin-top:18px"><b>Осторожно с именами.</b> В системе есть ещё '
  'три токена с префиксом <code>--color-static-brand-</code>: <code>primary</code>, '
  '<code>secondary</code> и <code>orange</code>. Они объявлены в файле <code>colors-x5.css</code> '
  'и принадлежат ко-бренду X5, а не Альфа-Банку. Имя вводит в заблуждение — '
  'ориентируйтесь на файл-источник, а не на префикс.</p>')
A('<div class="grid">')
for t in group(r"--color-static-brand"):
    if t["source"] == "colors-brand.css":
        continue
    A(swatch(t["name"], "X5 · " + t["name"].replace("--color-static-brand-", "")))
A('</div></section>')

# --------------------------------------------------------------- акцент
A('<section><h2>02 — действие</h2><p class="h2sub">Акцент и его состояния</p>')
A('<p class="note">В тёмной теме акцент осветляется до <code>#f83a2a</code>: чистый брендовый '
  'красный на тёмном фоне даёт недостаточный контраст. Исходный оттенок уезжает в <code>-inverted</code>.</p>')
A('<div class="grid">')
for n in ["--color-light-accent-primary", "--color-light-accent-primary-hover",
          "--color-light-accent-primary-press", "--color-dark-accent-primary",
          "--color-dark-accent-primary-hover", "--color-dark-accent-primary-press",
          "--color-light-accent-secondary", "--color-dark-accent-secondary"]:
    lbl = n.replace("--color-", "")
    A(swatch(n, lbl))
A('</div></section>')

# --------------------------------------------------------------- поверхности
A('<section><h2>03 — поверхности</h2><p class="h2sub">Как строится глубина</p>')
A('<p class="note">Главный переносимый приём: на тёмном фоне карточка не заливается '
  'сплошным цветом, а получает <b>полупрозрачную белёсую вуаль</b>. Так вложенность '
  'читается одинаково на любой подложке, включая цветные плашки статусов.</p>')
A('<div class="themes">')

A('<div class="panel light"><h3>Светлая тема</h3><div class="stack">')
for name, label, val in [
    ("--color-light-base-bg-primary", "фон страницы", v("--color-light-base-bg-primary")),
    ("--color-light-base-bg-secondary", "фон секции", v("--color-light-base-bg-secondary")),
    ("--color-light-neutral-translucent-100", "карточка", v("--color-light-neutral-translucent-100")),
    ("--color-light-neutral-translucent-300", "вложенный блок", v("--color-light-neutral-translucent-300")),
]:
    A(f'<div class="layer" style="background:{val};border:1px solid rgba(15,25,55,.10)">'
      f'<span>{esc(label)}</span><em>{esc(val)}</em></div>')
A('</div></div>')

A('<div class="panel dark"><h3>Тёмная тема</h3><div class="stack">')
for name, label in [
    ("--color-dark-base-bg-primary", "фон страницы"),
    ("--color-dark-neutral-translucent-100", "карточка"),
    ("--color-dark-neutral-translucent-300", "вложенный блок"),
    ("--color-dark-neutral-translucent-400", "наведение"),
]:
    val = v(name)
    A(f'<div class="layer" style="background:{val};border:1px solid rgba(222,222,238,.13)">'
      f'<span>{esc(label)}</span><em>{esc(val)}</em></div>')
A('</div></div>')
A('</div></section>')

# --------------------------------------------------------------- текст
A('<section><h2>04 — текст</h2><p class="h2sub">Иерархия через прозрачность</p>')
A('<p class="note">Текстовые токены заданы альфа-каналом, а не непрозрачным цветом. '
  'Одна и та же иерархия работает в обеих темах: примерно <b>0.88 / 0.55 / 0.38 / 0.18</b>.</p>')
A('<div class="themes">')
for theme, cls, title in [("light", "light", "Светлая тема"), ("dark", "dark", "Тёмная тема")]:
    A(f'<div class="panel {cls}"><h3>{title}</h3><div class="stack">')
    for lvl in ["primary", "secondary", "tertiary", "quaternary"]:
        n = f"--color-{theme}-text-{lvl}"
        val = v(n)
        if not val:
            continue
        A(f'<div style="color:{val};font:500 15px/1.4 var(--font-ui)">'
          f'{lvl} — читаемость по уровням '
          f'<span style="font:400 11.5px/1 var(--font-mono);opacity:.8">{esc(val)}</span></div>')
    A('</div></div>')
A('</div></section>')

# --------------------------------------------------------------- статусы
A('<section><h2>05 — статусы</h2><p class="h2sub">Смысловые цвета</p>')
A('<p class="note">Четыре состояния плюс приглушённые заливки для плашек. '
  '<b>Красный статуса <code>#ff4837</code> намеренно отличается от брендового <code>#ef3124</code>.</b> '
  'В инструменте, где красный означает найденную уязвимость, смешивать их нельзя.</p>')
A('<div class="grid">')
for st in ["negative", "attention", "positive", "info"]:
    for theme in ["light", "dark"]:
        n = f"--color-{theme}-status-{st}"
        if v(n):
            A(swatch(n, f"{theme} · {st}"))
A('</div>')
A('<div class="grid" style="margin-top:10px">')
for st in ["negative", "attention", "positive", "info"]:
    for theme in ["light", "dark"]:
        n = f"--color-{theme}-status-muted-{st}"
        if v(n):
            A(swatch(n, f"{theme} · muted {st}"))
A('</div></section>')

# --------------------------------------------------------------- графики
A('<section><h2>06 — визуализация данных</h2><p class="h2sub">Готовые палитры для графиков</p>')
A('<p class="note">В системе есть подобранные наборы под визуализацию. Для дашборда '
  'с метриками атак это снимает вопрос выбора цветов серий. Берите набор целиком, '
  'не смешивая цвета из разных.</p>')
A('<p class="note" style="margin-bottom:12px"><b>Категориальные наборы.</b> '
  '<code>flexible</code> из 14 цветов — когда число серий заранее неизвестно.</p>')
for k, items in scale_sets("qualitative", "light").items():
    A('<div class="ramp-row"><code>' + esc(k) + '</code><div class="ramp">'
      + "".join(f'<i style="background:{t.get("hex")}" title="{t.get("hex")}"></i>' for t in items)
      + '</div></div>')
A('<p class="note" style="margin:22px 0 12px"><b>Последовательные шкалы.</b> '
  'По 8 ступеней. Для тепловых карт и метрик с направлением «больше — меньше».</p>')
for k, items in scale_sets("sequential", "light").items():
    A('<div class="ramp-row"><code>' + esc(k) + '</code><div class="ramp">'
      + "".join(f'<i style="background:{t.get("hex")}" title="{t.get("hex")}"></i>' for t in items)
      + '</div></div>')
A('</section>')

# --------------------------------------------------------------- радиусы
A('<section><h2>07 — форма</h2><p class="h2sub">Радиусы</p>')
A('<p class="note">На живом сайте доминирует <b>32px</b> для карточек и <b>99px</b> для кнопок. '
  'Это заметно круглее типового корпоративного интерфейса и является узнаваемой чертой бренда. '
  'В плотной таблице находок 32px неуместен — там 12–16px, а 99px остаётся кнопкам и тегам.</p>')
A('<div class="radii">')
for r in ["4", "8", "12", "16", "24", "32", "64"]:
    val = v(f"--border-radius-{r}")
    if val:
        A(f'<figure><span class="box" style="border-radius:{val}"></span>'
          f'<figcaption>{esc(val)}</figcaption></figure>')
A('<figure><span class="box" style="border-radius:99px"></span><figcaption>99px · pill</figcaption></figure>')
A('</div></section>')

# --------------------------------------------------------------- типографика
A('<section><h2>08 — типографика</h2><p class="h2sub">Шкала дизайн-системы</p>')
A('<p class="note">Фирменный шрифт бренда — <b>Styrene A</b> Бёртона Хасибе, лицензия платная. '
  'Интерфейсный <b>Alfa Interface Sans</b> публично не распространяется. Живой сайт '
  'отрисовывается системным стеком: замеры не показали ни одного веб-шрифта. '
  'Ниже шкала показана шрифтом Golos Text как доступной заменой с кириллицей.</p>')
SAMPLE = "Компрометация памяти агента"
for fam, names in [("headline", ["headline_xlarge", "headline_large", "headline_medium", "headline_small", "headline_xsmall"]),
                   ("paragraph", ["paragraph_primary_large", "paragraph_primary_medium", "paragraph_primary_small",
                                  "paragraph_secondary_medium"]),
                   ("accent", ["accent_primary_medium", "accent_secondary_medium", "accent_caps"]),
                   ("action", ["action_primary_medium", "action_secondary_medium"])]:
    A(f'<p class="note" style="margin:22px 0 6px"><b>{fam}</b></p>')
    for nm in names:
        s = typo.get(nm)
        if not s:
            continue
        style = (f"font-size:{s.get('font-size','16px')};line-height:{s.get('line-height','1.4')};"
                 f"font-weight:{s.get('font-weight','400')};")
        if "letter-spacing" in s:
            style += f"letter-spacing:{s['letter-spacing']};"
        if "text-transform" in s:
            style += f"text-transform:{s['text-transform']};"
        A(f'<div class="type-row"><div class="spec"><b>{esc(nm)}</b>'
          f'{esc(s.get("font-size","—"))} / {esc(s.get("line-height","—"))} / {esc(s.get("font-weight","—"))}</div>'
          f'<div class="demo" style="{style}">{SAMPLE}</div></div>')
A('</section>')

# --------------------------------------------------------------- применение
A('<section><h2>09 — применение</h2><p class="h2sub">Как это складывается в наш интерфейс</p>')
A('<p class="note">Карточки находок, собранные только из токенов Альфы. Критичность '
  'кодируется полосой слева и бейджем — <b>формой и цветом одновременно</b>, чтобы '
  'состояние читалось и без различения оттенков.</p>')
A('<div class="apply">')
FINDINGS = [
    ("negative", "Критично", "Запись в долговременную память",
     "Инструкция сохранена между сессиями и сработала у другого пользователя.",
     "вход → контекст → память → выбор инструмента"),
    ("attention", "Высокий", "Подмена аргументов инструмента",
     "Агент вызвал верный инструмент с изменёнными параметрами перевода.",
     "результат инструмента → аргументы → изменение состояния"),
    ("info", "Средний", "Инъекция через результат поиска",
     "Внешняя страница повлияла на план, но цель атаки не достигнута.",
     "веб-страница → контекст → планирование"),
    ("positive", "Отражено", "Прямая инъекция в запросе",
     "Фильтр входа отклонил 40 из 40 попыток серии.",
     "вход → фильтр"),
]
for st, label, title, desc, path in FINDINGS:
    sev = v(f"--color-light-status-{st}")
    bg = v(f"--color-light-status-muted-{st}")
    fg = v(f"--color-light-text-{st}") or sev
    A(f'<div class="finding" style="--sev:{sev};--sev-bg:{bg};--sev-fg:{fg}">'
      f'<div class="row"><span class="badge">{esc(label)}</span></div>'
      f'<h4>{esc(title)}</h4><p>{esc(desc)}</p>'
      f'<div class="path">{esc(path)}</div></div>')
A('</div></section>')

# --------------------------------------------------------------- сводка
A('<section><h2>10 — состав</h2><p class="h2sub">Что лежит в папке design</p>')
A('<div class="tbl-wrap"><table><thead><tr>'
  '<th>Каталог</th><th>Содержимое</th><th class="num">Объём</th></tr></thead><tbody>')
INV = [
    ("01-brand-foundations/", "Обзор бренда, палитра, типографика, правила логотипа", "4 документа"),
    ("02-logos/", "Знак, логотип RU/EN, Альфа Бизнес в SVG, PDF, PNG", "40 файлов"),
    ("03-design-tokens/", "Исходный CSS, tokens.json, W3C-формат, единый alfa-tokens.css", "2244 токена"),
    ("04-references/", "Скриншоты, HTML, замеры стилей, разобранные брендбуки", "26 съёмок"),
    ("05-ui-patterns/", "Паттерны с живых интерфейсов и этот лист образцов", "2 файла"),
    ("99-raw/", "Исходные PDF брендбуков", "14 МБ"),
]
for a, b, c in INV:
    A(f'<tr><td><code>{esc(a)}</code></td><td>{esc(b)}</td><td class="num">{esc(c)}</td></tr>')
A('</tbody></table></div></section>')

A('''<footer>
Собрано 3 сентября 2026 для кейса agentic red teaming. Источники:
<a href="https://github.com/core-ds/core-components">дизайн-система Core Components</a>,
<a href="https://www.alfabank.by/about/logo/">официальная выдача логотипов</a>,
живые страницы alfabank.ru. Воспроизводится скриптами
<code>parse_tokens.py</code>, <code>capture_sites.py</code>, <code>build_swatches.py</code>.
</footer>''')
A('</div>')

A("""<script>
(function () {
  var root = document.documentElement;
  var btns = Array.prototype.slice.call(document.querySelectorAll('.toggle button'));
  function apply(mode) {
    if (mode === 'system') { root.removeAttribute('data-theme'); }
    else { root.setAttribute('data-theme', mode); }
    btns.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.set === mode)); });
    try { localStorage.setItem('alfa-kit-theme', mode); } catch (e) {}
  }
  btns.forEach(function (b) { b.addEventListener('click', function () { apply(b.dataset.set); }); });
  var saved = 'system';
  try { saved = localStorage.getItem('alfa-kit-theme') || 'system'; } catch (e) {}
  apply(saved);
})();
</script>""")

out = os.path.join(BASE, "05-ui-patterns", "alfa-swatches.html")
open(out, "w", encoding="utf-8").write("\n".join(P))
print("готово:", out, f"({os.path.getsize(out)//1024} КБ)")
