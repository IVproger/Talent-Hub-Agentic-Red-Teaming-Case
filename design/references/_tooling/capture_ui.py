#!/usr/bin/env python3
"""Съёмка текущего Streamlit UI: экраны, состояния, компоненты крупным планом.

Требует запущенное приложение и playwright с chromium.

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python3 output/_tooling/make_fixtures.py
    python3 -m streamlit run agentic_redteam/ui/app.py --server.port 8599

    python3 output/_tooling/capture_ui.py            # http://127.0.0.1:8599
    python3 output/_tooling/capture_ui.py 8502

Результат: output/01-screens/*.png и output/03-tokens/computed-styles.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1]
SCREENS = OUT / "01-screens"
TOKENS = OUT / "03-tokens"
SCREENS.mkdir(parents=True, exist_ok=True)
TOKENS.mkdir(parents=True, exist_ok=True)

PORT = sys.argv[1] if len(sys.argv) > 1 else "8599"
URL = f"http://127.0.0.1:{PORT}/"
DESKTOP = {"width": 1512, "height": 950}
TALL = {"width": 1512, "height": 2200}
NARROW = {"width": 1024, "height": 1400}

log: list[str] = []


def shot(page, name: str, selector=None) -> None:
    path = SCREENS / f"{name}.png"
    try:
        if selector is None:
            page.screenshot(path=str(path))
        elif isinstance(selector, str):
            page.locator(selector).first.screenshot(path=str(path))
        else:
            selector.screenshot(path=str(path))
        log.append(f"ok   {name}")
    except Exception as exc:  # съёмка референсов не должна падать целиком
        log.append(f"FAIL {name}: {type(exc).__name__}: {exc}")


def settle(page, ms: int = 2200) -> None:
    page.wait_for_timeout(ms)


def open_expander(page, text: str) -> bool:
    """Раскрыть expander, если он свёрнут; уже раскрытый не трогать."""
    try:
        block = page.locator(
            f'[data-testid="stExpander"]:has(summary:has-text("{text}"))'
        ).first
        details = block.locator('[data-testid="stExpanderDetails"]').first
        if not details.is_visible():
            block.locator("summary").first.click()
            settle(page, 900)
        return True
    except Exception as exc:
        log.append(f"FAIL expander {text}: {exc}")
        return False


JS_STYLES = r"""
() => {
  const pick = (el, props) => {
    if (!el) return null;
    const s = getComputedStyle(el);
    const out = {};
    for (const p of props) out[p] = s.getPropertyValue(p).trim();
    return out;
  };
  const box = ["font-family","font-size","font-weight","line-height","letter-spacing",
               "color","background-color","border","border-radius","padding","margin"];
  const rootStyle = getComputedStyle(document.documentElement);
  const vars = {};
  for (const name of ["--ink","--paper","--surface","--line","--muted"]) {
    const v = rootStyle.getPropertyValue(name).trim();
    if (v) vars[name] = v;
  }
  const targets = {
    "html": "html",
    "body": "body",
    "stApp": ".stApp",
    "block-container": ".block-container",
    "sidebar": '[data-testid="stSidebar"]',
    "h1.page-head": ".page-head h1",
    "p.page-head": ".page-head p",
    "h2.scenario-title": ".scenario-title h2",
    "h3": '[data-testid="stSidebar"] h3',
    "button.primary": '.stFormSubmitButton button[kind="primary"]',
    "button.secondary": '.stFormSubmitButton button:not([kind="primary"])',
    "input.text": '[data-testid="stTextInput"] input',
    "select": '[data-testid="stSelectbox"] [role="combobox"]',
    "expander": '[data-testid="stExpander"]',
    "tab": '[data-testid="stTab"]',
    "tab-selected": '[aria-selected="true"][role="tab"]',
    "dataframe": '[data-testid="stDataFrame"]',
    "alert": '[data-testid="stAlert"]',
    "result-summary": ".result-summary",
    "result-title-strong": ".result-title strong",
    "result-dt": ".result-summary dt",
    "result-dd": ".result-summary dd",
    "step-line": ".step-line",
    "trace-node": ".trace-node",
    "model-row": ".model-row",
    "check-row": ".check-row",
    "code": '[data-testid="stCode"]',
  };
  const computed = {};
  for (const [key, sel] of Object.entries(targets)) {
    computed[key] = pick(document.querySelector(sel), box);
  }
  const fonts = new Set(), colors = new Set(), bgs = new Set(), radii = new Set(), sizes = new Set();
  for (const el of Array.from(document.querySelectorAll("*")).slice(0, 4000)) {
    const s = getComputedStyle(el);
    fonts.add(s.fontFamily);
    colors.add(s.color);
    if (s.backgroundColor !== "rgba(0, 0, 0, 0)") bgs.add(s.backgroundColor);
    if (s.borderRadius !== "0px") radii.add(s.borderRadius);
    sizes.add(s.fontSize);
  }
  const sortPx = a => [...a].sort((x, y) => parseFloat(x) - parseFloat(y));

  // Каждый селектор из <style> приложения: сколько узлов он реально задевает.
  const authored = [
    '.stApp','.block-container','[data-testid="stHeader"]','[data-testid="stExpandSidebarButton"]',
    '[data-testid="stSidebar"]','.page-head','.scenario-meta','.config-source','.model-row',
    '.scenario-summary','.scenario-title','.step-line','.result-summary','.result-title',
    '.ratio-track','.trace-rail','.trace-node','.live-log','.live-row','.check-row',
    '[data-testid="stAlert"]','.stAlertContainer','[data-testid="stExpander"]','[data-testid="stCode"]',
    '.stButton>button','.stDownloadButton>button','.stFormSubmitButton>button',
    '[data-baseweb="select"]>div','[data-testid="stTextInput"] input','[data-testid="stNumberInput"] input',
    '[data-baseweb="tab-list"]','[data-baseweb="tab"]','[aria-selected="true"][role="tab"]',
    '[data-testid="stDataFrame"]','[data-testid="stProgressBar"]>div>div','[data-testid="stIconMaterial"]',
  ];
  const selectorMatches = {};
  for (const sel of authored) {
    try { selectorMatches[sel] = document.querySelectorAll(sel).length; }
    catch (e) { selectorMatches[sel] = "invalid"; }
  }

  return {
    selectorMatches,
    cssVariables: vars,
    computed,
    inUse: {
      fontFamilies: [...fonts].sort(),
      colors: [...colors].sort(),
      backgrounds: [...bgs].sort(),
      borderRadii: sortPx(radii),
      fontSizes: sortPx(sizes),
    },
  };
}
"""


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=DESKTOP, device_scale_factor=2)
        page.goto(URL, wait_until="networkidle")
        settle(page, 4000)

        # --- 1. состояние по умолчанию -------------------------------------
        shot(page, "01-default-desktop")
        shot(page, "02-sidebar-default", '[data-testid="stSidebar"]')
        shot(page, "03-main-empty-state", '[data-testid="stMain"]')
        shot(page, "04-page-header", ".page-head")
        shot(page, "05-scenario-summary", ".scenario-summary")

        # --- 2. раскрытые блоки сайдбара -----------------------------------
        open_expander(page, "Модели из конфигурации")
        shot(page, "06-sidebar-models-expanded", '[data-testid="stSidebar"]')
        shot(page, "07-component-model-rows", ".config-source")
        open_expander(page, "Контекст цели")
        settle(page, 900)
        page.set_viewport_size(TALL)
        settle(page, 1200)
        shot(page, "08-sidebar-target-context", '[data-testid="stSidebar"]')
        page.set_viewport_size(DESKTOP)
        settle(page, 900)

        # --- 3. другой сценарий (scripted) ---------------------------------
        try:
            page.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first.click()
            settle(page, 700)
            page.get_by_role("option").nth(2).click()
            settle(page, 2500)
            shot(page, "09-scenario-scripted-desktop")
            shot(page, "10-scenario-scripted-summary", ".scenario-summary")
        except Exception as exc:
            log.append(f"FAIL scenario switch: {exc}")

        # --- 4. preflight: реальный прогон проверок (стенд не поднят) ------
        try:
            page.get_by_role("button", name="ПРОВЕРИТЬ").first.click()
            page.wait_for_timeout(9000)
            shot(page, "11-preflight-failed-sidebar", '[data-testid="stSidebar"]')
            shot(page, "12-component-check-rows", '[data-testid="stSidebar"] [data-testid="stExpander"]:has(.check-row)')
            shot(page, "13-preflight-failed-desktop")
        except Exception as exc:
            log.append(f"FAIL preflight: {exc}")

        # --- 5. валидация формы: одинаковые CUS ----------------------------
        try:
            inputs = page.locator('[data-testid="stSidebar"] [data-testid="stTextInput"] input')
            inputs.nth(1).fill("1001")
            page.get_by_role("button", name="ПРОВЕРИТЬ").first.click()
            page.wait_for_timeout(9000)
            shot(page, "14-form-validation-error", '[data-testid="stSidebar"]')
            inputs.nth(1).fill("1002")
            page.get_by_role("button", name="ПРОВЕРИТЬ").first.click()
            page.wait_for_timeout(9000)
        except Exception as exc:
            log.append(f"FAIL validation: {exc}")

        # --- 6. история запусков -------------------------------------------
        page.set_viewport_size(TALL)
        settle(page, 1200)
        open_expander(page, "История запусков")
        settle(page, 1500)
        shot(page, "15-history-expanded", '[data-testid="stMain"]')
        shot(page, "16-component-history-table", '[data-testid="stMain"] [data-testid="stDataFrame"]')

        # --- 7. загрузка сохранённого прогона -> вкладки результата --------
        # Первый в списке — прерванный прогон: состояние INCOMPLETE.
        try:
            page.get_by_role("button", name="ОТКРЫТЬ", exact=True).first.click()
            page.wait_for_timeout(4000)
            settle(page, 1500)
            shot(page, "17-result-incomplete-tall")
            shot(page, "17b-component-result-summary-incomplete", ".result-summary")
        except Exception as exc:
            log.append(f"FAIL open failed run: {exc}")
        # Второй — завершённый прогон: состояние COMPROMISED.
        try:
            open_expander(page, "История запусков")
            settle(page, 1200)
            page.locator(
                '[data-testid="stSelectbox"]:has([data-testid="stWidgetLabel"]'
                ':has-text("Сохранённый запуск"))'
            ).first.click()
            settle(page, 800)
            page.get_by_role("option").last.click()
            settle(page, 2500)
            page.get_by_role("button", name="ОТКРЫТЬ", exact=True).first.click()
            page.wait_for_timeout(4000)
            settle(page, 1500)
            shot(page, "17c-result-compromised-tall")
            page.set_viewport_size(DESKTOP)
            settle(page, 1200)
            shot(page, "18-result-tab-outcome-desktop")
            shot(page, "19-component-result-summary", ".result-summary")
            shot(page, "20-component-tabs", '[data-testid="stTabs"] [role="tablist"]')
            shot(page, "20b-component-form-controls", '[data-testid="stSidebar"] [data-testid="stForm"]')
        except Exception as exc:
            log.append(f"FAIL open run: {exc}")

        # --- 8. вкладка ТРЕЙС ----------------------------------------------
        try:
            page.get_by_role("tab", name="ТРЕЙС").click()
            settle(page, 2000)
            page.set_viewport_size(TALL)
            settle(page, 1500)
            shot(page, "21-result-tab-trace-tall")
            shot(page, "22-component-trace-rail", ".trace-rail")
            shot(page, "23-component-attempts-table", '[data-testid="stMain"] [data-testid="stDataFrame"]')
            step = page.locator('[data-testid="stMain"] [data-testid="stExpander"]').first
            shot(page, "24-component-step-expander", step)
            tables = page.locator('[data-testid="stMain"] [data-testid="stDataFrame"]:visible')
            if tables.count() > 1:
                shot(page, "24b-component-assertions-table", tables.last)
            shot(
                page,
                "24c-component-run-picker",
                '[data-testid="stSelectbox"]:has([data-testid="stWidgetLabel"]:has-text("Прогон"))',
            )
        except Exception as exc:
            log.append(f"FAIL trace tab: {exc}")

        # --- 9. вкладки ОТЧЁТ и ФАЙЛЫ --------------------------------------
        try:
            page.get_by_role("tab", name="ОТЧЁТ").click()
            settle(page, 2000)
            shot(page, "25-result-tab-report-tall")
        except Exception as exc:
            log.append(f"FAIL report tab: {exc}")
        try:
            page.set_viewport_size(DESKTOP)
            settle(page, 1200)
            page.get_by_role("tab", name="ФАЙЛЫ").click()
            settle(page, 2000)
            shot(page, "26-result-tab-files-desktop")
            shot(page, "27-component-download-buttons", '[data-testid="stMain"] [data-testid="stVerticalBlock"]:has([data-testid="stDownloadButton"])')
        except Exception as exc:
            log.append(f"FAIL files tab: {exc}")

        # --- 10. узкий экран -----------------------------------------------
        try:
            page.get_by_role("tab", name="РЕЗУЛЬТАТ").click()
            settle(page, 1500)
            page.set_viewport_size(NARROW)
            settle(page, 2000)
            shot(page, "28-narrow-1024")
        except Exception as exc:
            log.append(f"FAIL narrow: {exc}")

        # --- 11. токены и реально применённые стили ------------------------
        try:
            page.set_viewport_size(DESKTOP)
            settle(page, 1200)
            data = page.evaluate(JS_STYLES)
            (TOKENS / "computed-styles.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            log.append("ok   computed-styles.json")
        except Exception as exc:
            log.append(f"FAIL computed styles: {exc}")

        browser.close()

    print("\n".join(log))


if __name__ == "__main__":
    main()
