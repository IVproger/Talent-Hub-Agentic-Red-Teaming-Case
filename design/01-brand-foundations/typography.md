# Типографика

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


### key

| Стиль | Размер | Интерлиньяж | Насыщенность | Трекинг |
| --- | --- | --- | --- | --- |
| `key_large` | 120px | 132px | 500 | — |
| `key_medium` | 96px | 120px | 500 | — |
| `key_small` | 80px | 96px | 500 | — |
| `key_xlarge` | 144px | 180px | 500 | — |
| `key_xsmall` | 64px | 80px | 500 | — |

### headline

| Стиль | Размер | Интерлиньяж | Насыщенность | Трекинг |
| --- | --- | --- | --- | --- |
| `headline_large` | 40px | 48px | 500 | — |
| `headline_medium` | 32px | 40px | 500 | — |
| `headline_small` | 24px | 32px | 500 | — |
| `headline_xlarge` | 48px | 64px | 500 | — |
| `headline_xsmall` | 20px | 24px | 500 | — |

### promo

| Стиль | Размер | Интерлиньяж | Насыщенность | Трекинг |
| --- | --- | --- | --- | --- |
| `promo_large` | 40px | 48px | 400 | — |
| `promo_medium` | 32px | 40px | 400 | — |
| `promo_small` | 24px | 32px | 400 | — |
| `promo_xlarge` | 48px | 64px | 400 | — |
| `promo_xsmall` | 20px | 24px | 400 | — |

### accent

| Стиль | Размер | Интерлиньяж | Насыщенность | Трекинг |
| --- | --- | --- | --- | --- |
| `accent_caps` | 12px | 16px | 700 | 1.25px |
| `accent_component` | 16px | 20px | 700 | — |
| `accent_component_primary` | 16px | 20px | 700 | — |
| `accent_component_secondary` | 14px | 18px | 700 | — |
| `accent_primary_large` | 18px | 24px | 700 | — |
| `accent_primary_medium` | 16px | 24px | 700 | — |
| `accent_primary_small` | 14px | 20px | 700 | — |
| `accent_secondary_large` | 13px | 16px | 700 | — |
| `accent_secondary_medium` | 12px | 16px | 700 | — |
| `accent_secondary_small` | 11px | 16px | 700 | — |
| `accent_tagline` | 12px | 16px | 700 | 1.25px |

### action

| Стиль | Размер | Интерлиньяж | Насыщенность | Трекинг |
| --- | --- | --- | --- | --- |
| `action_caps` | 12px | 16px | 500 | 1.25px |
| `action_component` | 16px | 20px | 500 | — |
| `action_component_primary` | 16px | 20px | 500 | — |
| `action_component_secondary` | 14px | 18px | 500 | — |
| `action_primary_large` | 18px | 24px | 500 | — |
| `action_primary_medium` | 16px | 24px | 500 | — |
| `action_primary_small` | 14px | 20px | 500 | — |
| `action_secondary_large` | 13px | 16px | 500 | — |
| `action_secondary_medium` | 12px | 16px | 500 | — |
| `action_secondary_small` | 11px | 16px | 500 | — |
| `action_tagline` | 12px | 16px | 500 | 1.25px |

### paragraph

| Стиль | Размер | Интерлиньяж | Насыщенность | Трекинг |
| --- | --- | --- | --- | --- |
| `paragraph_caps` | 12px | 16px | 400 | 1.25px |
| `paragraph_component` | 16px | 20px | 400 | — |
| `paragraph_component_primary` | 16px | 20px | 400 | — |
| `paragraph_component_secondary` | 14px | 18px | 400 | — |
| `paragraph_primary_large` | 18px | 24px | 400 | — |
| `paragraph_primary_medium` | 16px | 24px | 400 | — |
| `paragraph_primary_small` | 14px | 20px | 400 | — |
| `paragraph_secondary_large` | 13px | 16px | 400 | — |
| `paragraph_secondary_medium` | 12px | 16px | 400 | — |
| `paragraph_secondary_small` | 11px | 16px | 400 | — |
| `paragraph_tagline` | 12px | 16px | 400 | 1.25px |

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
