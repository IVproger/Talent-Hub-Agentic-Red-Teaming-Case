# Баннеры и итог отчёта

## `.mk-banner--success`
positive-muted, radius 16, padding 16×20, gap 14. `__icon` 32 круг positive-dot «✓»; `__title` 15/600 positive; `__sub` 13 rgba(3,3,6,.7). Компактный вариант (документ сформирован): padding 14×16, справа `.mk-btn--dark.mk-btn--small`.

## Итог отчёта · `.mk-card--flush`
1. `.mk-verdict` — padding 22×24, border-bottom: `.mk-label` «Итог» · `.mk-hero-verdict` COMPROMISED (моно 28/700 .02em negative) · `.mk-sev--critical` · имя сценария справа (13 secondary).
2. `.mk-metrics` — grid 4; `__cell` padding 16×24, border-right; подпись 12 secondary + `.mk-metric` моно 22/600 (cross-user «да» — negative).
3. `.mk-asr-bar` 4px bg-page, `__fill` negative-bar шириной = ASR.

Значения вердикта: COMPROMISED (есть PROVEN), RESISTED (нет).
