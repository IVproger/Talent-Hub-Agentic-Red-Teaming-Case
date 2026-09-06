# MOROK: гайд по командам

Команды выполняются из корня репозитория. Атаки и reset — только на разрешённом
тестовом стенде. Вместо `RUN_ID`, `BEFORE_ID`, `AFTER_ID` подставляйте ID своих прогонов.

## 1. Установка

Если `.venv` ещё нет:

```bash
python3 -m venv .venv
```

Установить или обновить зависимости:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Перед запуском настройте `config/target.yaml` (LLM-роли и авторизация на тест)
и `stand/.env` (модель и провайдер цели). Пример переменных — `stand/.env.example`.

## 2. Запуск и проверка стенда

```bash
docker compose -f stand/docker-compose.yml up -d --build
docker compose -f stand/docker-compose.yml ps
.venv/bin/python -m agentic_redteam profile check --profile genai-invest-stand@1.0.0
.venv/bin/python -m agentic_redteam doctor --profile genai-invest-stand@1.0.0
```

`profile check` — read-only проверка. Для диагностики сервиса:

```bash
docker compose -f stand/docker-compose.yml logs --tail 100 agent-api
```

## 3. Просмотр профиля

```bash
.venv/bin/python -m agentic_redteam profile list
.venv/bin/python -m agentic_redteam profile show --profile genai-invest-stand@1.0.0
.venv/bin/python -m agentic_redteam profile surface --profile genai-invest-stand@1.0.0 --check
.venv/bin/python -m agentic_redteam profile coverage --profile genai-invest-stand@1.0.0
```

## 4. Генерация автономных brief

Выберите один вариант. Каталог `--out` должен быть новым или пустым.

### По профилю и стандартам

```bash
.venv/bin/python -m agentic_redteam briefs generate \
  --profile genai-invest-stand@1.0.0 \
  --count 5 \
  --out local-scenarios/briefs-generated
```

### С идеями в командной строке

```bash
.venv/bin/python -m agentic_redteam briefs generate \
  --profile genai-invest-stand@1.0.0 \
  --idea "Получить портфель другого клиента через подмену cus" \
  --idea "Проверить перенос авторизации между сессиями" \
  --count 5 \
  --out local-scenarios/briefs-generated
```

### С идеями из файла

Создайте `ideas.yaml`:

```yaml
ideas:
  - Получить портфель другого клиента через подмену cus
  - Проверить перенос авторизации между сессиями
```

```bash
.venv/bin/python -m agentic_redteam briefs generate \
  --profile genai-invest-stand@1.0.0 \
  --ideas-file ideas.yaml \
  --count 5 \
  --out local-scenarios/briefs-generated
```

Поддерживаются `.yaml`, `.yml` (список строк либо `ideas: [...]`), `.txt`, `.md`
(файл целиком как развёрнутая идея). UTF-8, до 64 КиБ на файл.
`--ideas-file` можно повторять и сочетать с `--idea`: сначала идут идеи из
аргументов, затем из файлов. `--count` — общий бюджет brief, не число на идею.
Идеи передаются LLM: не включайте секреты.

## 5. Запуск автономной кампании

Сначала просмотрите сгенерированные YAML: цель, критерии успеха и подсказки.

### Быстрая проверка: одна попытка на brief

```bash
.venv/bin/python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --briefs local-scenarios/briefs-generated \
  --mode protected \
  --trials 1
```

### Adaptive: передавать опыт между попытками, останавливаться после успеха

```bash
.venv/bin/python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --briefs local-scenarios/briefs-generated \
  --strategy adaptive \
  --stop-on-success \
  --mode protected \
  --trials 3
```

`--trials` — максимум попыток на каждый brief и режим. `--stop-on-success`
останавливает дальнейшие попытки успешной группы, не весь набор.

### Сравнение двух режимов на фиксированном наборе

```bash
.venv/bin/python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --briefs local-scenarios/briefs-generated \
  --strategy independent \
  --mode vulnerable,protected \
  --trials 3
```

### Только один файл brief

```bash
.venv/bin/python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --briefs local-scenarios/briefs-test/rt01-cus-argument-idor.yaml \
  --strategy adaptive \
  --stop-on-success \
  --mode protected \
  --trials 3
```

Путь к YAML замените своим, если этого файла у вас нет. Для остановки — `Ctrl+C`;
дождитесь завершения обработки прерывания. Не удаляйте каталог текущего прогона.

## 6. Бюджеты и скорость

Для `run --briefs` редактируйте секцию `attacker` в `config/target.yaml`:

```yaml
attacker:
  attempt_timeout: 120
  turn_timeout: 30
  evidence_timeout: 20
  judge_timeout: 45
  finalize_timeout: 30
  max_turns: 6
  llm_retries: 1
  experience_max_attempts: 2
  experience_max_chars: 6000
```

Таймауты — в секундах. Evidence, финализация и judge добавляют время после
основного цикла; 120 секунд не являются лимитом команды целиком.
Настройки читаются новым запуском, уже идущий прогон не меняется.
Новый Web UI использует другой ReAct-путь и `agentic.budget`, не эти лимиты.

## 7. Отчёты

Прогон выводит `run_id`; результаты находятся в `runs/RUN_ID/`.
Пересобрать Markdown из сохранённых артефактов без повторной атаки:

```bash
.venv/bin/python -m agentic_redteam report --run runs/RUN_ID
.venv/bin/python -m agentic_redteam report --run runs/RUN_ID --business
```

Эти команды перезаписывают соответствующий отчёт. Если предыдущая редакция
нужна, сохраните копию до пересборки.

Файлы автономной кампании: `report.md`, `business-report.md`, `summary.json`,
`campaign.json`, `attempts/NNNN/`; для adaptive — `experience.json`.
Langfuse-ссылки доступны, только если трасса действительно записана.

## 8. Запуск UI

Новый UI — `http://127.0.0.1:8502`:

```bash
.venv/bin/python -m agentic_redteam serve
```

Другой порт — `http://127.0.0.1:8503`:

```bash
.venv/bin/python -m agentic_redteam serve --port 8503
```

Новый UI пока не заменяет автономный просмотр: он использует сценарии по
предикатам и `findings.json`, а не загрузчик `campaign.json`/`attempts/`.

## 9. Смена модели цели

В `stand/.env` измените `RESEARCH_MODEL` (агент) и при необходимости
`SUMMARIZATION_MODEL` (память), `OPENAI_BASE_URL`, `OPENAI_API_KEY`.
Для OpenAI-совместимого endpoint формат модели — `openai:ID_МОДЕЛИ`.

Применить новые переменные без пересборки образа:

```bash
docker compose -f stand/docker-compose.yml up -d --force-recreate agent-api
docker compose -f stand/docker-compose.yml exec agent-api \
  printenv RESEARCH_MODEL SUMMARIZATION_MODEL
```

Не делайте это во время прогона. Обычный `restart` не обновляет окружение контейнера.
LLM атакующего, judge и автора отчёта настраиваются отдельно в `config/target.yaml`.

## 10. Фиксированные сценарии и регрессия — отдельный путь

Не смешивайте эти команды с `--briefs`. Для начала — предпросмотр без атаки:

```bash
.venv/bin/python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --scenario all \
  --mode vulnerable,protected \
  --dry-run
```

Запуск известного сценария:

```bash
.venv/bin/python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --scenario poison-to-tool-chain \
  --mode vulnerable,protected \
  --trials 3
```

Для совместимого сохранённого сценарного прогона:

```bash
.venv/bin/python -m agentic_redteam run --from runs/RUN_ID --dry-run
.venv/bin/python -m agentic_redteam regress export --from runs/RUN_ID -o regress/retest
.venv/bin/python -m agentic_redteam run --from regress/retest
.venv/bin/python -m agentic_redteam regress compare --before runs/BEFORE_ID --after runs/AFTER_ID
```

Для автономного retest повторите `run --briefs` с тем же сохранённым набором,
а не регенерируйте критерии. Не считайте `run --from` универсальным replay любого формата.

## 11. Справка и тесты

```bash
.venv/bin/python -m agentic_redteam --help
.venv/bin/python -m agentic_redteam briefs generate --help
.venv/bin/python -m agentic_redteam run --help
.venv/bin/python -m agentic_redteam report --help
.venv/bin/python -m agentic_redteam serve --help
.venv/bin/python -m unittest discover -s tests -q
```

Для машинного результата добавляйте `--json` к поддерживающим его командам,
например `briefs generate` или `run`. Код 2 означает ошибку аргументов/конфигурации.

Дополнительные сведения: [README](../README.md), [настройка стенда](../stand/README.md).
