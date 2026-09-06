#!/usr/bin/env python3
"""Вынуть из agentic_redteam/ui/app.py всё, что относится к оформлению.

Пишет:
  output/04-source/styles.css        — CSS из `_styles()`, по одному правилу в строку
  output/04-source/app.py            — снимок исходника UI на момент съёмки
  output/03-tokens/design-tokens.json — токены темы Streamlit + CSS-переменные
  output/03-tokens/current-theme.toml — копия .streamlit/config.toml

    python3 output/_tooling/extract_styles.py
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "output"
APP = REPO_ROOT / "agentic_redteam" / "ui" / "app.py"
THEME = REPO_ROOT / ".streamlit" / "config.toml"

SOURCE = OUT / "04-source"
TOKENS = OUT / "03-tokens"
SOURCE.mkdir(parents=True, exist_ok=True)
TOKENS.mkdir(parents=True, exist_ok=True)


def extract_css(source: str) -> str:
    match = re.search(r"<style>(.*?)</style>", source, re.S)
    if not match:
        raise SystemExit("В app.py не найден блок <style>")
    css = match.group(1)
    lines = [line.strip() for line in css.splitlines()]
    return "\n".join(line for line in lines if line) + "\n"


def parse_theme(text: str) -> dict:
    theme: dict[str, str] = {}
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "theme" and "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            theme[key.strip()] = value.strip().strip('"')
    return theme


def main() -> None:
    source = APP.read_text(encoding="utf-8")
    css = extract_css(source)
    (SOURCE / "styles.css").write_text(
        "/* Извлечено из agentic_redteam/ui/app.py -> _styles().\n"
        "   Единственный источник оформления в продукте: один st.markdown\n"
        "   с unsafe_allow_html=True. Правки здесь ни на что не влияют. */\n\n"
        + css,
        encoding="utf-8",
    )
    shutil.copyfile(APP, SOURCE / "app.py")

    theme = parse_theme(THEME.read_text(encoding="utf-8"))
    shutil.copyfile(THEME, TOKENS / "current-theme.toml")

    css_vars = dict(re.findall(r"(--[a-z-]+)\s*:\s*([^;]+);", css))
    font_sizes = sorted({m for m in re.findall(r"font-size\s*:\s*([\d.]+rem)", css)}, key=float_rem)
    spacing = sorted({m for m in re.findall(r"(?:padding|margin|gap)\s*:\s*([^;]+);", css)})

    payload = {
        "streamlitTheme": theme,
        "cssVariables": css_vars,
        "fontStacks": {
            "app": '"JetBrains Mono","SFMono-Regular",Consolas,monospace',
            "webfont": "JetBrains Mono 400/500/600/700 c fonts.googleapis.com",
            "icons": '"Material Symbols Rounded"',
        },
        "fontSizesInCss": font_sizes,
        "spacingValuesInCss": spacing,
        "radii": {"authored": "0 (border-radius:0 на кнопках, alert, code, expander)"},
        "customComponentClasses": sorted(set(re.findall(r"\.([a-z][a-z-]+)\s*[,{ ]", css))),
    }
    (TOKENS / "design-tokens.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"styles.css      {len(css.splitlines())} строк")
    print(f"css variables   {len(css_vars)}")
    print(f"font sizes      {len(font_sizes)}")


def float_rem(value: str) -> float:
    return float(value.replace("rem", ""))


if __name__ == "__main__":
    main()
