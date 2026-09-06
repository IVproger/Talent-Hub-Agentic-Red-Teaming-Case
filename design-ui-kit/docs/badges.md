# Бейджи, теги, статусы

## Вердикты · `.mk-badge`
Моно 11/600, padding 3×9, radius 99.

| Модификатор | Фон | Текст |
|---|---|---|
| `--proven`, `--fail` | negative-muted | negative |
| `--not-proven`, `--pass` | positive-muted | positive |
| `--running` | info-muted | info + `mk-pulse` 1.2s |
| `--pending` | fill-secondary | text-secondary |

## Критичность · `.mk-sev`
Golos 11/700 uppercase .04em. `--critical` negative · `--high` attention · `--none` («Отражено») positive.

## Теги поверхности · `.mk-tag`
2×8, 11/600. По умолчанию bg-page; `--memory` attention; `--mcp` info.

## Статус с точкой · `.mk-status`
Точка 7px через ::before. По умолчанию text-tertiary («не проверено»); `--ok` positive-dot/positive; `--info` info (точка входа).

Отдельная точка — `.mk-dot` (`--ok`, `--info`, `--bad`); в сайдбаре 6px.
