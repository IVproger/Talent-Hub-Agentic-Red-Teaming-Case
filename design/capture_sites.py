#!/usr/bin/env python3
"""
Захват UI-референсов экосистемы Альфа-Банка.

Для каждого URL:
  - полностраничный скриншот (desktop 1440 + mobile 390), JPEG q90;
    мобильные приводятся к 1x, иначе файлы весят десятки мегабайт
  - сохранённый HTML
  - извлечение CSS custom properties (:root), реально используемых
    font-family, цветов и радиусов со страницы

Запуск:  python3 capture_sites.py
Результат: 04-references/screenshots/, 04-references/html-snapshots/,
           04-references/extracted/
"""
import json
import os
import re
import sys
import time
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(BASE, "04-references", "screenshots")
HTML = os.path.join(BASE, "04-references", "html-snapshots")
EXTRACT = os.path.join(BASE, "04-references", "extracted")
for d in (SHOTS, HTML, EXTRACT):
    os.makedirs(d, exist_ok=True)

# (slug, url, что это в экосистеме бренда)
TARGETS = [
    ("alfabank-ru-main",        "https://alfabank.ru/",                                   "Главный сайт банка (розница)"),
    ("alfabank-ru-cards",       "https://alfabank.ru/everyday/debit-cards/",              "Продуктовый листинг: дебетовые карты"),
    ("alfabank-ru-credit",      "https://alfabank.ru/get-money/credit/",                  "Продуктовый листинг: кредиты"),
    ("alfabank-ru-invest",      "https://alfabank.ru/make-money/investments/",            "Альфа-Инвестиции"),
    ("alfabank-ru-sme",         "https://alfabank.ru/sme/",                               "Альфа-Бизнес (МСБ)"),
    ("alfabank-ru-corporate",   "https://alfabank.ru/corporate/",                         "Корпоративный блок"),
    ("alfabank-ru-about",       "https://alfabank.ru/about/",                             "О банке / корпоративная страница"),
    ("alfabank-ru-career",      "https://job.alfabank.ru/",                               "Карьерный портал (HR-бренд)"),
    ("alfabank-by",             "https://www.alfabank.by/",                               "Альфа-Банк Беларусь"),
    ("alfabank-by-logo",        "https://www.alfabank.by/about/logo/",                    "Официальная страница выдачи логотипов"),
    ("coreds-storybook",        "https://core-ds.github.io/core-components/master/",      "Storybook дизайн-системы Core Components"),
    ("coreds-github",           "https://github.com/core-ds/core-components",             "Репозиторий дизайн-системы"),
    ("alfa-habr",               "https://habr.com/ru/companies/alfa/articles/",           "Инженерный блог Alfa Digital"),
]

JS_EXTRACT = r"""
() => {
  const out = {rootVars:{}, fonts:{}, colors:{}, bgColors:{}, radii:{}, shadows:{}, fontSizes:{}};

  // 1) CSS custom properties, объявленные в :root / html / body
  try {
    for (const sheet of Array.from(document.styleSheets)) {
      let rules;
      try { rules = sheet.cssRules; } catch(e) { continue; }
      if (!rules) continue;
      for (const rule of Array.from(rules)) {
        if (!rule.selectorText || !rule.style) continue;
        if (!/^(:root|html|body)\b/.test(rule.selectorText)) continue;
        for (const prop of Array.from(rule.style)) {
          if (prop.startsWith('--')) out.rootVars[prop] = rule.style.getPropertyValue(prop).trim();
        }
      }
    }
  } catch(e) {}

  // 2) реально применённые стили на видимых элементах
  const els = Array.from(document.querySelectorAll('body *')).slice(0, 4000);
  const bump = (o,k) => { if(!k) return; o[k] = (o[k]||0)+1; };
  for (const el of els) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const cs = getComputedStyle(el);
    bump(out.fonts, cs.fontFamily);
    bump(out.fontSizes, cs.fontSize + ' / ' + cs.fontWeight + ' / ' + cs.lineHeight);
    if (el.textContent && el.textContent.trim()) bump(out.colors, cs.color);
    const bg = cs.backgroundColor;
    if (bg && bg !== 'rgba(0, 0, 0, 0)') bump(out.bgColors, bg);
    if (cs.borderRadius && cs.borderRadius !== '0px') bump(out.radii, cs.borderRadius);
    if (cs.boxShadow && cs.boxShadow !== 'none') bump(out.shadows, cs.boxShadow);
  }
  const top = (o,n) => Object.entries(o).sort((a,b)=>b[1]-a[1]).slice(0,n)
                        .map(([k,v])=>({value:k, count:v}));
  return {
    rootVars: out.rootVars,
    fonts: top(out.fonts, 15),
    fontSizes: top(out.fontSizes, 30),
    textColors: top(out.colors, 30),
    bgColors: top(out.bgColors, 30),
    radii: top(out.radii, 20),
    shadows: top(out.shadows, 15),
    title: document.title,
    h1: Array.from(document.querySelectorAll('h1,h2')).slice(0,25).map(e=>e.innerText.trim()).filter(Boolean),
    nav: Array.from(document.querySelectorAll('header a, nav a')).slice(0,60).map(e=>e.innerText.trim()).filter(Boolean),
  };
}
"""


def capture(page, slug, url, note, viewport_tag):
    rec = {"slug": slug, "url": url, "note": note, "viewport": viewport_tag}
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
    except Exception as e:
        rec["error"] = f"goto: {type(e).__name__}: {str(e)[:200]}"
        print(f"  !! {slug} [{viewport_tag}] goto failed: {rec['error']}")
        return rec

    # даём время JS-челленджу (ServicePipe) и ленивой загрузке
    for _ in range(3):
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
            break
        except Exception:
            pass
    time.sleep(3)

    # прокрутка для ленивых блоков
    try:
        page.evaluate("""async () => {
            const step = window.innerHeight;
            for (let y = 0; y < Math.min(document.body.scrollHeight, 12000); y += step) {
                window.scrollTo(0, y); await new Promise(r => setTimeout(r, 220));
            }
            window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 600));
        }""")
    except Exception:
        pass

    rec["final_url"] = page.url
    rec["title"] = page.title()

    shot = os.path.join(SHOTS, f"{slug}--{viewport_tag}.png")
    try:
        page.screenshot(path=shot, full_page=True, timeout=45000)
        rec["screenshot"] = os.path.relpath(shot, BASE)
    except Exception as e:
        try:
            page.screenshot(path=shot, full_page=False, timeout=30000)
            rec["screenshot"] = os.path.relpath(shot, BASE) + " (viewport only)"
        except Exception as e2:
            rec["screenshot_error"] = str(e2)[:200]

    # Полностраничные PNG весят десятки мегабайт и раздувают репозиторий.
    # Приводим мобильные к 1x и пересохраняем в JPEG: объём падает примерно
    # в три раза при визуально неотличимом результате.
    if os.path.exists(shot):
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            im = Image.open(shot)
            if viewport_tag == "mobile":
                im = im.resize((im.size[0] // 2, im.size[1] // 2), Image.LANCZOS)
            jpg = shot[:-4] + ".jpg"
            im.convert("RGB").save(jpg, "JPEG", quality=90, optimize=True, progressive=True)
            im.close()
            os.remove(shot)
            rec["screenshot"] = os.path.relpath(jpg, BASE)
        except ImportError:
            rec["screenshot_note"] = "pillow не установлен, PNG оставлен как есть"
        except Exception as e:
            rec["screenshot_note"] = f"сжатие не выполнено: {str(e)[:120]}"

    if viewport_tag == "desktop":
        try:
            html = page.content()
            with open(os.path.join(HTML, f"{slug}.html"), "w", encoding="utf-8") as f:
                f.write(html)
            rec["html_bytes"] = len(html)
        except Exception as e:
            rec["html_error"] = str(e)[:200]
        try:
            data = page.evaluate(JS_EXTRACT)
            with open(os.path.join(EXTRACT, f"{slug}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            rec["extracted"] = {
                "rootVars": len(data.get("rootVars", {})),
                "fonts": [f["value"] for f in data.get("fonts", [])[:3]],
            }
        except Exception as e:
            rec["extract_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return rec


def main():
    only = sys.argv[1:] or None
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--ignore-certificate-errors", "--disable-blink-features=AutomationControlled"])
        for viewport_tag, vp in (("desktop", {"width": 1440, "height": 1000}),
                                 ("mobile", {"width": 390, "height": 844})):
            ctx = browser.new_context(
                viewport=vp,
                ignore_https_errors=True,
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
                device_scale_factor=2 if viewport_tag == "mobile" else 1,
            )
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            page = ctx.new_page()
            for slug, url, note in TARGETS:
                if only and slug not in only:
                    continue
                print(f"[{viewport_tag}] {slug} -> {url}", flush=True)
                results.append(capture(page, slug, url, note, viewport_tag))
            ctx.close()
        browser.close()

    with open(os.path.join(EXTRACT, "_capture-log.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    ok = sum(1 for r in results if r.get("screenshot"))
    print(f"\nDONE: {ok}/{len(results)} captures with screenshots")


if __name__ == "__main__":
    main()
