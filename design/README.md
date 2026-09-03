# design/ — основа дизайн-кита

Собранные референсы, брендовые активы и дизайн-токены Альфа-Банка для кейса
agentic red teaming. Всё, что здесь лежит, получено 3 сентября 2026 года
из открытых источников и воспроизводится скриптами из этой же папки.

## С чего начать

| Если вам нужно | Откройте |
| --- | --- |
| Понять бренд и ограничения | [01-brand-foundations/brand-overview.md](01-brand-foundations/brand-overview.md) |
| Увидеть палитру глазами | [05-ui-patterns/alfa-swatches.html](05-ui-patterns/alfa-swatches.html) — открыть в браузере |
| Взять цвета в код | [03-design-tokens/alfa-tokens.css](03-design-tokens/alfa-tokens.css) |
| Принять решения по дизайну | [design-kit-brief.md](design-kit-brief.md) |
| Найти конкретный скриншот | [04-references/site-inventory.md](04-references/site-inventory.md) |

## Состав

```text
design/
├── README.md                    этот файл
├── design-kit-brief.md          выводы, решения и открытые вопросы к заказчику
│
├── 01-brand-foundations/        текстовая основа
│   ├── brand-overview.md        бренд, история айдентики, цветовая стратегия
│   ├── color-palette.md         полная палитра с токенами (генерируется)
│   ├── typography.md            шрифты и шкала из 48 стилей (генерируется)
│   └── logo-usage.md            файлы логотипа и правила использования
│
├── 02-logos/                    40 официальных файлов
│   ├── znak_svg|pdf|png/        знак «А», 4 цветовые версии
│   ├── logotip_svg|pdf|png/     логотип с названием, RU и EN
│   └── logo-a-biznes-svg|…/     суббренд «Альфа Бизнес»
│
├── 03-design-tokens/            2244 актуальных токена
│   ├── vars-css/                29 исходных CSS из репозитория банка
│   ├── alfa-tokens.css          единый файл, только актуальные токены
│   ├── tokens.json              полный дамп с source и deprecated
│   ├── tokens-active.json       актуальные, с разрешёнными алиасами
│   ├── tokens.w3c.json          формат W3C Design Tokens для Figma
│   ├── typography-scale.json    48 стилей типографики
│   ├── palette-summary.json     сводка по группам
│   └── core-components-packages.txt   132 компонента дизайн-системы
│
├── 04-references/               снятые интерфейсы
│   ├── site-inventory.md        что снято, зачем и как читать
│   ├── screenshots/             26 JPEG, десктоп и мобильный
│   ├── html-snapshots/          13 HTML после выполнения скриптов
│   ├── extracted/               13 JSON с замерами + сводный лог
│   ├── brandbook-text/          текст двух брендбуков
│   └── brandbook-pages/         107 страниц брендбуков картинками
│
├── 05-ui-patterns/
│   ├── ui-patterns.md           приёмы, снятые с живых интерфейсов
│   └── alfa-swatches.html       визуальный лист образцов, обе темы
│
├── 99-raw/                      исходные PDF, 14 МБ
│
├── capture_sites.py             съёмка сайтов через Playwright
├── parse_tokens.py              разбор CSS-токенов в JSON и W3C
├── build_docs.py                генерация палитры и типографики в Markdown
└── build_swatches.py            генерация листа образцов
```

Файлы, помеченные «генерируется», перезаписываются скриптами. Правки в них
пропадут — меняйте генератор.

## Воспроизведение

```bash
cd design

# 1. обновить токены из репозитория дизайн-системы банка
python3 parse_tokens.py

# 2. пересобрать документацию
python3 build_docs.py

# 3. пересобрать визуальный лист образцов
python3 build_swatches.py

# 4. переснять сайты целиком или одну цель
python3 capture_sites.py
python3 capture_sites.py alfabank-ru-corporate
```

Зависимости: `pymupdf` для разбора PDF, `playwright` и `pillow` для съёмки.
Браузер ставится командой `python3 -m playwright install chromium`.

## Три вещи, которые стоит знать до работы с этим материалом

**Альфа-Банк не красный.** Замеры живых страниц показывают, что фирменный
красный занимает считанные проценты площади. Доминируют почти чёрный,
белый и светло-серый. Красить интерфейс в красный — ошибка.

**Тёмная тема у бренда своя.** Корпоративный раздел сайта свёрстан целиком
в тёмной теме, и его цвета совпадают с токенами `--color-dark-*`. Тёмный
дашборд для инструмента безопасности не будет чужеродным.

**Имя токена не равно его принадлежности.** Три токена с префиксом
`--color-static-brand-` приходят из файла `colors-x5.css` и принадлежат
ко-бренду X5, а не Альфе. Проверяйте поле `source` в `tokens.json`.

## Источники

| Что | Где |
| --- | --- |
| Дизайн-система Core Components | [github.com/core-ds/core-components](https://github.com/core-ds/core-components) |
| Storybook компонентов | [core-ds.github.io/core-components](https://core-ds.github.io/core-components/master/) |
| Официальная выдача логотипов | [alfabank.by/about/logo](https://www.alfabank.by/about/logo/) |
| Основной сайт | [alfabank.ru](https://alfabank.ru/) |
| Инженерный блог | [habr.com/ru/companies/alfa](https://habr.com/ru/companies/alfa/) |

## Правовая оговорка

Логотипы и фирменный стиль принадлежат АО «Альфа-Банк». Материалы собраны
из открытого доступа для работы над кейсом заказчика. Дизайн-система
Core Components распространяется под лицензией MIT. Шрифт Styrene A требует
коммерческой лицензии и в комплект не входит. Перед публичным использованием
макетов запросите у заказчика официальный брендбук и разрешение.
