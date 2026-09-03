#!/usr/bin/env python3
"""
Разбор CSS-токенов дизайн-системы Альфа-Банка (Core Components / @alfalab/core-components-vars)
в машиночитаемые форматы для переиспользования в нашем дизайн-ките.

Архитектура токенов Альфы (важно для понимания вывода):
  * Базовые палитры (colors-bluetint, -monochrome, -qualitative, -sequential,
    -decorative, -promo, -pfm) объявляют СРАЗУ обе темы: --color-light-* и --color-dark-*.
  * Файлы *-dark.css — это ПЕРЕКЛЮЧАТЕЛЬ темы: они переопределяют
    --color-light-X: var(--color-dark-X). Их не нужно парсить как значения.
  * --color-static-* не зависят от темы.
  * colors-indigo.css — предыдущее поколение темы, целиком deprecated. Оставлен
    в полном дампе для сверки, но исключён из актуального набора.

На вход: 03-design-tokens/vars-css/*.css
На выход:
  03-design-tokens/tokens.json          — все токены (с source, deprecated, theme)
  03-design-tokens/tokens-active.json   — актуальные, тема bluetint + модульные палитры
  03-design-tokens/tokens.w3c.json      — формат W3C Design Tokens (Figma / Style Dictionary)
  03-design-tokens/alfa-tokens.css      — один CSS только с актуальными токенами
  03-design-tokens/palette-summary.json — сводка по группам для документации
"""
import json
import os
import re
from collections import OrderedDict, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "03-design-tokens", "vars-css")
OUT = os.path.join(BASE, "03-design-tokens")

DECL = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*(.*?);", re.S)

# Файлы-переключатели темы: содержат только алиасы var(), не значения.
THEME_SWITCH = {f for f in os.listdir(SRC) if f.endswith("-dark.css")} if os.path.isdir(SRC) else set()
# Устаревшее поколение темы.
LEGACY = {"colors-indigo.css", "shadows-indigo.css", "colors-addons.css"}


def parse():
    """Возвращает список токенов. Ключ уникальности — (source, name), а не name,
    иначе файлы затирают друг друга при алфавитном обходе."""
    rows = []
    for fn in sorted(os.listdir(SRC)):
        if not fn.endswith(".css"):
            continue
        text = open(os.path.join(SRC, fn), encoding="utf-8").read()
        # deprecated помечается комментарием сразу после значения
        for m in DECL.finditer(text):
            name = m.group(1)
            raw = m.group(2)
            tail = text[m.end():m.end() + 40]
            dep = bool(re.match(r"\s*/\*\s*deprecated", tail, re.I))
            value = re.sub(r"/\*.*?\*/", "", raw, flags=re.S).strip()
            value = re.sub(r"\s+", " ", value)
            if not value:
                continue
            parts = name.lstrip("-").split("-")
            theme = "static"
            if len(parts) > 1 and parts[1] in ("light", "dark"):
                theme = parts[1]
            rows.append(OrderedDict(
                name=name,
                value=value,
                theme=theme,
                source=fn,
                is_alias=value.startswith("var("),
                deprecated=dep,
                legacy_file=fn in LEGACY,
                theme_switch_file=fn in THEME_SWITCH,
            ))
    return rows


HEX3 = re.compile(r"^#([0-9a-fA-F]{3})$")
HEX6 = re.compile(r"^#([0-9a-fA-F]{6})$")
RGBF = re.compile(r"^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)\s*(?:[,/]\s*([\d.%]+)\s*)?\)$")


def to_hex(value):
    """Нормализует цвет -> (#rrggbb, alpha) либо (None, None)."""
    v = value.strip()
    m = HEX3.match(v)
    if m:
        return "#" + "".join(c * 2 for c in m.group(1)).lower(), 1.0
    m = HEX6.match(v)
    if m:
        return "#" + m.group(1).lower(), 1.0
    if v.startswith("#") and len(v) == 9:
        return "#" + v[1:7].lower(), round(int(v[7:9], 16) / 255, 3)
    m = RGBF.match(v)
    if m:
        r, g, b = (int(round(float(m.group(i)))) for i in (1, 2, 3))
        a = m.group(4)
        alpha = 1.0 if a is None else (round(float(a[:-1]) / 100, 3) if a.endswith("%") else round(float(a), 3))
        return "#%02x%02x%02x" % (r, g, b), alpha
    return None, None


def w3c_type(name, value):
    if to_hex(value)[0] or name.startswith("--color"):
        return "color"
    if "shadow" in name:
        return "shadow"
    if "font-family" in name:
        return "fontFamily"
    if name.startswith(("--gap", "--border-radius", "--size", "--safe-area")) or re.match(r"^[\d.]+(px|em|rem)$", value):
        return "dimension"
    return "other"


VARREF = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*([^)]*))?\)")


def resolve(rows):
    """Разворачивает var(--x) до конкретного значения.

    Семантический слой Альфы (--color-light-bg-*, --color-light-text-* и т.д.)
    почти целиком построен на алиасах к базовой шкале neutral/status. Без
    разрешения ссылок мы теряем именно тот слой, которым и надо пользоваться.
    """
    lookup = {}
    for t in rows:
        if t["deprecated"] or t["legacy_file"] or t["theme_switch_file"]:
            continue
        lookup.setdefault(t["name"], t["value"])

    def deref(value, depth=0):
        if depth > 12:
            return value
        m = VARREF.search(value)
        if not m:
            return value
        ref, fallback = m.group(1), (m.group(2) or "").strip()
        target = lookup.get(ref, fallback)
        if not target:
            return value
        return deref(VARREF.sub(target, value, count=1), depth + 1)

    for t in rows:
        if t["is_alias"]:
            r = deref(t["value"])
            if r != t["value"]:
                t["resolved"] = r
    return rows


def main():
    rows = resolve(parse())
    for t in rows:
        h, a = to_hex(t.get("resolved") or t["value"])
        if h:
            t["hex"], t["alpha"] = h, a

    # Актуальный набор: не deprecated, не legacy-файл, не файл-переключатель.
    # Алиасы СОХРАНЯЕМ — это и есть семантический слой; они разрешены полем "resolved".
    active = [t for t in rows
              if not t["deprecated"] and not t["legacy_file"]
              and not t["theme_switch_file"]]

    json.dump(rows, open(os.path.join(OUT, "tokens.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(active, open(os.path.join(OUT, "tokens-active.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---- W3C Design Tokens ----
    tree = {}
    for t in active:
        parts = t["name"].lstrip("-").split("-")
        node = tree
        for p in parts[:-1]:
            node = node.setdefault(p, {})
            if not isinstance(node, dict):
                break
        else:
            leaf = parts[-1]
            if isinstance(node, dict) and not isinstance(node.get(leaf), dict):
                node[leaf] = {"$value": t.get("hex") or t["value"],
                              "$type": w3c_type(t["name"], t["value"])}
    json.dump(tree, open(os.path.join(OUT, "tokens.w3c.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---- единый CSS ----
    by_src = defaultdict(list)
    for t in active:
        by_src[t["source"]].append(t)
    with open(os.path.join(OUT, "alfa-tokens.css"), "w", encoding="utf-8") as f:
        f.write("/* Актуальные токены дизайн-системы Альфа-Банка (тема bluetint + модульные палитры).\n"
                "   Источник: github.com/core-ds/core-components -> packages/vars/src\n"
                "   Сгенерировано design/parse_tokens.py — не редактировать вручную.\n"
                "   Для тёмной темы дополнительно подключите vars-css/colors-*-dark.css. */\n\n:root {\n")
        for src in sorted(by_src):
            f.write(f"\n    /* ---- {src} ---- */\n")
            for t in by_src[src]:
                f.write(f"    {t['name']}: {t['value']};\n")
        f.write("}\n")

    # ---- сводка ----
    groups = defaultdict(lambda: {"count": 0, "themes": set(), "sample": []})
    for t in active:
        key = "-".join(t["name"].lstrip("-").split("-")[:3])
        g = groups[key]
        g["count"] += 1
        g["themes"].add(t["theme"])
        if t.get("hex") and len(g["sample"]) < 6:
            g["sample"].append({"name": t["name"], "hex": t["hex"], "alpha": t["alpha"]})
    summary = {k: {"count": v["count"], "themes": sorted(v["themes"]), "sample": v["sample"]}
               for k, v in sorted(groups.items(), key=lambda x: -x[1]["count"])}
    json.dump(summary, open(os.path.join(OUT, "palette-summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    uniq = {t["hex"] for t in active if t.get("hex")}
    print(f"всего объявлений:   {len(rows)}")
    print(f"актуальных:         {len(active)}")
    print(f"уникальных hex:     {len(uniq)}")
    by_theme = defaultdict(int)
    for t in active:
        by_theme[t["theme"]] += 1
    print(f"по темам:           {dict(by_theme)}")
    print("\nГруппы актуальных токенов:")
    for k, v in list(summary.items())[:30]:
        print(f"  {k:<38} {v['count']:>4}  [{','.join(v['themes'])}]")
    return rows, active


if __name__ == "__main__":
    main()
