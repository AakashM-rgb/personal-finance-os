"""Financial AI Assistant orchestration - the ONLY place a user's question
reaches an AI provider, and the ONLY caller of app.ai.tools.registry for a
conversational request. See app.ai for the full architecture:

    Authenticated user
        -> AI Assistant API (app.api.v1.ai)
        -> this orchestration service
        -> app.ai.tools.registry (the only allowlisted-tool choke point)
        -> existing authorized repositories/services
        -> database

The AI model itself (app.ai.provider) never touches a database session, an
ORM object, or a caller-supplied user_id - every tool call it proposes is
validated and executed here with the user_id taken from the authenticated
request context, and a tool's real result is the only source of any fact
that can appear in the final answer.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.base import ConversationMessage, ToolDefinition, ToolOutcome
from app.ai.provider.factory import get_ai_provider
from app.ai.tools.catalog import TOOL_CATALOG
from app.ai.tools.registry import validate_and_execute
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.ai import DISCLAIMER, AssistantMessageInput, AssistantResponse, ToolUsage

# Bounds how many times the provider may ask for another round of tools
# before this turn gives up - a real or misbehaving provider can never
# drive an unbounded number of tool calls/database queries for one request.
_MAX_TOOL_ROUNDS = 4

_SYSTEM_PROMPT = """You are the Financial AI Assistant inside a personal finance app.

You can only see the user's financial data through the tools you're given - you have no other \
access to it and must never guess, estimate, or invent a transaction, balance, budget, goal, \
subscription, or any other financial fact. Every number in your answer must come from a tool \
result you actually received in this conversation.

Rules:
- If a question needs data, call the relevant tool(s) before answering. Never answer from \
assumption when a tool could supply the real figure.
- If a tool result is empty, missing, or an error, say plainly: "There is not enough data to \
answer that reliably." Do not fill the gap with a guess.
- If the question cannot be answered with the available tools at all, say so explicitly and \
suggest the kinds of questions you can answer instead.
- For any question involving a financial decision (e.g. "can I afford X", "how much should I \
save"), clearly separate: what the data shows (fact), what you calculated from it \
(calculation), what you assumed (assumption), and any general guideline you're citing \
(estimate) - label each one.
- Never guarantee a return, promise an outcome, or claim certainty about the future.
- You are not a licensed financial advisor and must never claim to be one.
- Keep answers concise and grounded in real numbers, formatted plainly (no markdown tables)."""


def _tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(name=spec.name, description=spec.description, input_schema=spec.input_schema)
        for spec in TOOL_CATALOG
    ]


def _history_to_conversation(history: list[AssistantMessageInput]) -> list[ConversationMessage]:
    return [ConversationMessage(role=item.role, text=item.content) for item in history]


async def ask(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AssistantMessageInput] | None = None,
) -> AssistantResponse:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    ai_enabled = settings.ai_enabled if settings is not None else True
    provider = get_ai_provider()

    if not ai_enabled:
        # Refused before any tool is even proposed - never just a hidden
        # chat UI, see app.ai.tools.registry.validate_and_execute for the
        # second, independent enforcement of this same setting.
        return AssistantResponse(
            answer=(
                "AI access to your financial data is turned off for this account. "
                "Enable it in Settings to use the assistant."
            ),
            tools_used=[],
            provider=provider.name,
            disclaimer=DISCLAIMER,
        )

    conversation = _history_to_conversation(history or [])
    conversation.append(ConversationMessage(role="user", text=message))

    tools = _tool_definitions()
    tools_used: list[ToolUsage] = []

    for _round in range(_MAX_TOOL_ROUNDS):
        turn = await provider.next_turn(
            system_prompt=_SYSTEM_PROMPT, conversation=conversation, tools=tools
        )
        if turn.is_final:
            return AssistantResponse(
                answer=turn.text or "",
                tools_used=tools_used,
                provider=provider.name,
                disclaimer=DISCLAIMER,
            )

        conversation.append(
            ConversationMessage(role="assistant", text=turn.text, tool_calls=turn.tool_calls)
        )

        outcomes: list[ToolOutcome] = []
        for call in turn.tool_calls:
            result = await validate_and_execute(
                db,
                user_id=user_id,
                ai_enabled=ai_enabled,
                tool_name=call.name,
                raw_arguments=call.arguments,
            )
            tools_used.append(ToolUsage(tool_name=call.name, ok=result.ok))
            outcomes.append(
                ToolOutcome(
                    tool_call_id=call.id,
                    name=call.name,
                    output=(result.data or {}) if result.ok else {"error": result.error_message},
                    is_error=not result.ok,
                )
            )
        conversation.append(ConversationMessage(role="user", tool_outcomes=tuple(outcomes)))

    return AssistantResponse(
        answer="I couldn't complete that request. Please try rephrasing your question.",
        tools_used=tools_used,
        provider=provider.name,
        disclaimer=DISCLAIMER,
    )
