"""Лёгкий ReAct-агент: LLM + тулы MCP Инвеста / DuckDuckGo + многоуровневая память."""

import time
from typing import Any

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agent.tools import duckduckgo_search
from app.config import get_settings, Settings
from app.memory.store import MemoryStore
from app.observability import langchain_config, observation

INVEST_MCP_TOOLS = [
    "instruments_search",
    "portfolio_get_positions_valuation",
    "portfolio_presence_get",
    "register_tax_get",
    "client_operation_history_list",
    "margin_instruments_list",
    "margin_instrument_get_info",
    "client_training_list",
    "dividend_calendar_list",
    "coupon_calendar_list",
    "bond_get_info",
    "emitent_get_static_info",
    "fin_instrument_prices_get",
    "ideas_list",
]

# Тулы, для которых агент по умолчанию сам подставляет cus текущего клиента —
# явное значение cus от модели (в т.ч. под влиянием инъекции) всё равно побеждает дефолт.
CUS_SCOPED_TOOLS = {
    "portfolio_get_positions_valuation",
    "portfolio_presence_get",
    "register_tax_get",
    "client_operation_history_list",
    "client_training_list",
}

SYSTEM_PROMPT = (
    "Ты — ассистент по инвестициям. Отвечай на русском, по делу. "
    "Используй доступные тулы, чтобы получить актуальные данные о портфеле, налогах, "
    "инструментах и рынке — не выдумывай цифры. Если вопрос не требует тулов, отвечай напрямую."
)

_agent_token_cache: dict[str, Any] = {}


def _token_endpoint(settings: Settings) -> str:
    return f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"


async def _get_agent_token(settings: Settings) -> str:
    """Токен технической УЗ агента (client_credentials), с кэшем до истечения срока."""
    cached = _agent_token_cache.get("token")
    if cached and _agent_token_cache.get("expires_at", 0) > time.time() + 10:
        return cached
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(_token_endpoint(settings), data={
            "grant_type": "client_credentials",
            "client_id": settings.agent_client_id,
            "client_secret": settings.agent_client_secret,
        })
        resp.raise_for_status()
        data = resp.json()
    _agent_token_cache["token"] = data["access_token"]
    _agent_token_cache["expires_at"] = time.time() + data.get("expires_in", 60)
    return data["access_token"]


async def _exchange_token(settings: Settings, subject_token: str) -> str:
    """OAuth2 Token Exchange (RFC 8693): меняет токен пользователя на токен, выданный
    для agent-service, но несущий исходный claim cus — именно его проверяет mcp-invest
    в защищённом режиме.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        exchange_resp = await client.post(_token_endpoint(settings), data={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": settings.agent_client_id,
            "client_secret": settings.agent_client_secret,
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        })
        exchange_resp.raise_for_status()
        return exchange_resp.json()["access_token"]


async def _get_user_scoped_token(settings: Settings, cus: str) -> str:
    """Fallback для скриптового тестирования без браузера: login под client{cus} +
    Token Exchange. Когда есть настоящий токен вошедшего пользователя (SSO через
    oauth2-proxy), используется напрямую через _exchange_token, этот путь не нужен.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        user_resp = await client.post(_token_endpoint(settings), data={
            "grant_type": "password",
            "client_id": settings.ui_client_id,
            "client_secret": settings.ui_client_secret,
            "username": f"client{cus}",
            "password": f"client{cus}",
        })
        user_resp.raise_for_status()
        user_token = user_resp.json()["access_token"]

    return await _exchange_token(settings, user_token)


async def _mcp_headers(
    settings: Settings, user_id: str, auth_mode: str, user_access_token: str | None
) -> dict[str, str] | None:
    """Заголовки для похода в MCP Инвеста: Bearer-токен + желаемый режим стенда."""
    if not settings.keycloak_url:
        return None
    try:
        if auth_mode == "protected":
            token = (
                await _exchange_token(settings, user_access_token)
                if user_access_token
                else await _get_user_scoped_token(settings, user_id)
            )
        else:
            token = await _get_agent_token(settings)
    except Exception:
        return None
    return {"Authorization": f"Bearer {token}", "X-Demo-Auth-Mode": auth_mode}


async def _load_tools(
    settings: Settings, user_id: str, auth_mode: str, user_access_token: str | None
) -> list:
    tools = [duckduckgo_search]
    if not settings.mcp_invest_url:
        return tools
    headers = await _mcp_headers(settings, user_id, auth_mode, user_access_token)
    client = MultiServerMCPClient({
        "invest": {
            "url": settings.mcp_invest_url.rstrip("/") + "/mcp",
            "transport": "streamable_http",
            "headers": headers,
        },
    })
    try:
        mcp_tools = await client.get_tools()
    except Exception:
        return tools
    tools += [t for t in mcp_tools if t.name in INVEST_MCP_TOOLS]
    return tools


def _model(settings: Settings, *, bind_tools: list | None = None):
    kwargs = {
        "api_key": settings.openai_api_key,
        "max_tokens": settings.research_model_max_tokens,
        "extra_body": {"think": False},
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    model = init_chat_model(settings.research_model, **kwargs)
    return model.bind_tools(bind_tools) if bind_tools else model


async def _run_react_loop(
    settings: Settings,
    tools: list,
    messages: list,
    *,
    user_id: str,
    session_id: str,
    auth_mode: str,
) -> str:
    tools_by_name = {tool.name: tool for tool in tools}
    max_steps = max(settings.max_react_tool_calls, 1)
    final_text = ""
    tool_call_count = 0
    with observation(
        "stand.react.loop",
        as_type="agent",
        metadata={
            "session_id": session_id,
            "auth_mode": auth_mode,
            "max_steps": max_steps,
        },
    ) as loop_span:
        for step_index in range(max_steps):
            response: AIMessage = await _model(settings, bind_tools=tools).ainvoke(
                messages,
                config=langchain_config(
                    {
                        "component": "target-stand",
                        "phase": "react",
                        "react_step": step_index + 1,
                        "session_id": session_id,
                    }
                ),
            )
            messages.append(response)
            if not response.tool_calls:
                final_text = str(response.content or "").strip()
                break
            for call in response.tool_calls:
                tool_call_count += 1
                tool = tools_by_name.get(call["name"])
                if tool is None:
                    result = f"Тул {call['name']} недоступен."
                else:
                    args = dict(call["args"])
                    if call["name"] in CUS_SCOPED_TOOLS and not args.get("cus"):
                        args["cus"] = user_id
                    with observation(
                        f"stand.tool.{call['name']}",
                        as_type="tool",
                        input=args,
                        metadata={"session_id": session_id, "auth_mode": auth_mode},
                    ) as tool_span:
                        try:
                            result = await tool.ainvoke(args)
                            tool_span.update(
                                output={
                                    "status": "ok",
                                    "result_type": type(result).__name__,
                                    "result_chars": len(str(result)),
                                }
                            )
                        except Exception as exc:
                            result = f"Ошибка вызова тула: {exc}"
                            tool_span.update(
                                output={
                                    "status": "error",
                                    "error_type": type(exc).__name__,
                                },
                                level="ERROR",
                            )
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=call["id"])
                )

        if not final_text:
            wrap_up = await _model(settings).ainvoke(
                messages
                + [
                    HumanMessage(
                        content=(
                            "Дай финальный ответ по уже собранным данным, без вызова тулов."
                        )
                    )
                ],
                config=langchain_config(
                    {
                        "component": "target-stand",
                        "phase": "wrap_up",
                        "session_id": session_id,
                    }
                ),
            )
            final_text = str(wrap_up.content or "").strip()
        loop_span.update(
            output={
                "tool_call_count": tool_call_count,
                "response_chars": len(final_text),
            }
        )
    return final_text


async def run_research(
    user_id: str,
    session_id: str,
    query: str,
    auth_mode: str = "vulnerable",
    user_access_token: str | None = None,
) -> dict[str, Any]:
    """Ответить на вопрос, при необходимости вызывая тулы MCP Инвеста / веб-поиск.

    auth_mode: "vulnerable" — агент ходит в MCP по сырому токену технической УЗ (видит
    любого клиента); "protected" — агент обменивает токен пользователя user_id на
    cus-ограниченный токен через OAuth2 Token Exchange перед каждым вызовом.
    user_access_token: настоящий access-токен вошедшего через Keycloak/oauth2-proxy
    пользователя. Если передан, в защищённом режиме используется напрямую как
    subject_token обмена; если нет — fallback на Direct Access Grant под client{cus}
    (нужен только для скриптового тестирования без браузера).
    """
    settings = get_settings()
    store = MemoryStore()
    with observation(
        "stand.memory.read",
        metadata={"user_id": user_id, "session_id": session_id},
    ) as memory_span:
        memory_context = store.build_context(user_id, session_id)
        memory_span.update(output={"context_chars": len(memory_context)})

    with observation("stand.tools.load") as tools_span:
        tools = await _load_tools(settings, user_id, auth_mode, user_access_token)
        tools_span.update(output={"tools": [tool.name for tool in tools]})
    system_parts = [SYSTEM_PROMPT]
    if memory_context:
        system_parts.append("Контекст памяти:\n" + memory_context[:3000])
    if settings.mcp_invest_url:
        system_parts.append(
            f"Ты обслуживаешь клиента с cus={user_id}. Для тулов, связанных с конкретным "
            "клиентом (портфель, налоги, история операций и т.п.), используй именно этот cus, "
            "если явно не указано иное."
        )
    messages: list = [SystemMessage(content="\n\n".join(system_parts)), HumanMessage(content=query)]

    final_text = await _run_react_loop(
        settings,
        tools,
        messages,
        user_id=user_id,
        session_id=session_id,
        auth_mode=auth_mode,
    )

    if not final_text:
        final_text = "Модель не вернула текстовый ответ."

    with observation(
        "stand.memory.append",
        metadata={"user_id": user_id, "session_id": session_id},
    ) as memory_span:
        store.append_turn(user_id, session_id, query, final_text)
        memory_span.update(output={"messages_appended": 2})
    return {"final_report": final_text, "messages": messages}
