# Live-проверка W3C/Langfuse — 2026-09-05

Цель проверки — доказать не просто создание trace раннером, а продолжение
контекста внутри целевого агента через реальную HTTP-границу.

## Окружение и запуск

- Langfuse `4.30.0`, локальный compose из `deploy/langfuse/`;
- профиль `genai-invest-stand@1.0.0`;
- сценарий `bac-tool-argument`, режимы `vulnerable,protected`, по одной попытке;
- project keys переданы раннеру и `stand-agent-api`, секреты не сохранялись в
  Git и не записывались в этот протокол.

```bash
docker compose --env-file deploy/langfuse/.env \
  -f deploy/langfuse/docker-compose.yml up -d
docker compose -f stand/docker-compose.yml up -d \
  --no-deps --force-recreate agent-api
python -m agentic_redteam run \
  --profile genai-invest-stand@1.0.0 \
  --scenario bac-tool-argument \
  --mode vulnerable,protected --trials 1 --json
```

Результат кампании: run `20260905-192427-e7f221`, статус `completed`, ASR 50%,
одна state-доказанная находка. Локальный `observability.json` содержит:

- trace ID `8ff45f3b1396f50fbe4e3b16c1603079`;
- root observation ID `8d78a2ae81bf0216`;
- URL локальной трассы без credentials.

Каталог `runs/` и `.env` намеренно игнорируются Git; идентификаторы здесь —
операционный протокол, а не переносимый артефакт или секрет.

## Проверка дерева

Наблюдения читались через Langfuse v4 public API:

```bash
curl --fail --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "http://localhost:3001/api/public/v2/observations?traceId=8ff45f3b1396f50fbe4e3b16c1603079&limit=100"
```

API вернул 19 observations с одним `traceId`. Для обеих попыток подтверждено:

```text
redteam.run
└── campaign.attempt
    └── stand.chat
        ├── stand.memory.read
        ├── stand.tools.load
        ├── stand.react.loop
        │   ├── ChatOpenAI
        │   └── stand.tool.portfolio_get_positions_valuation
        └── stand.memory.append
```

Критерий пройден: `stand.chat` имеет `campaign.attempt` родителем, а внутренние
target-spans — потомки `stand.chat`. Совпадения одного trace ID без этих parent
links было бы недостаточно для доказательства сквозного распространения.

## Граница вывода

Langfuse остаётся fail-open телеметрией и не участвует в security verdict.
State-verdict кампании по-прежнему строится из локального evidence. Проверка
подтверждает W3C propagation и экспорт spans, но не закрывает отдельные задачи
живого `memory poisoning → foreign tool call → proven` и второго target.
