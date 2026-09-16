"""Provider-agnostic conversation/tool-call data model, plus the
`AIProvider` protocol every provider (mock or real) implements.

A provider NEVER receives a database session or ORM access, and never sees
anything about the user except plain conversational text and tool RESULTS
the orchestration service already fetched through the validated tool layer
(see app.services.ai_assistant_service, the only caller of a provider, and
app.ai.tools.registry, the only caller of a tool executor).
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolOutcome:
    tool_call_id: str
    name: str
    output: dict[str, Any]
    is_error: bool


@dataclass(frozen=True)
class ConversationMessage:
    """One turn of the conversation as a provider sees it.

    A role="user" message carries either the human's own text OR the
    results of tools the assistant asked for a moment ago (never both). A
    role="assistant" message carries the assistant's own prior text and/or
    the tool calls it requested.
    """

    role: Role
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    tool_outcomes: tuple[ToolOutcome, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderTurn:
    """Either `tool_calls` is non-empty (the provider wants tools run
    before it can answer) or `text` is the final answer - never both."""

    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    text: str | None = None

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


@runtime_checkable
class AIProvider(Protocol):
    """`name` is a safe, non-secret label surfaced to the frontend (e.g.
    "mock" or "anthropic") so the UI can honestly indicate demo mode - see
    CLAUDE.md: "never fabricate an AI response to look real"."""

    name: str

    async def next_turn(
        self,
        *,
        system_prompt: str,
        conversation: list[ConversationMessage],
        tools: list[ToolDefinition],
    ) -> ProviderTurn: ...
