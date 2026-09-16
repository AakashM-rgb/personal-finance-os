"""The real external AI provider seam. This class only ever runs when
ANTHROPIC_API_KEY is actually configured (see app.ai.provider.factory) -
the `anthropic` SDK is an optional dependency (`pip install .[ai]`),
imported lazily here so the base application, tests, and local development
never need it installed just to import this module (same pattern as
app.storage.s3.S3StorageProvider for boto3).

This provider never sees a database session, an ORM object, or a
caller-supplied user_id - it only ever receives plain conversation text and
the JSON-serializable RESULTS of tool calls the orchestration service
already validated and executed through app.ai.tools.registry. It proposes
tool calls by name/arguments only; it never executes anything itself.
"""

import json
from typing import Any

from app.ai.provider.base import ConversationMessage, ProviderTurn, ToolCall, ToolDefinition
from app.core.errors import AppError


class AnthropicConfigurationError(AppError):
    """Raised when AnthropicProvider is selected but the SDK isn't
    installed - a clear configuration error, never a silent fallback to a
    pretend response."""


def _to_anthropic_messages(conversation: list[ConversationMessage]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for message in conversation:
        if message.role == "user" and message.tool_outcomes:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": outcome.tool_call_id,
                            "content": _json_text(outcome.output),
                            "is_error": outcome.is_error,
                        }
                        for outcome in message.tool_outcomes
                    ],
                }
            )
        elif message.role == "assistant" and message.tool_calls:
            content: list[dict[str, Any]] = []
            if message.text:
                content.append({"type": "text", "text": message.text})
            content.extend(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                for call in message.tool_calls
            )
            messages.append({"role": "assistant", "content": content})
        else:
            messages.append({"role": message.role, "content": message.text or ""})
    return messages


def _json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, default=str)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, api_key: str, model: str) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise AnthropicConfigurationError(
                "ANTHROPIC_API_KEY is set but the optional 'anthropic' dependency is not "
                "installed. Install it with: pip install .[ai]"
            ) from exc

        self._model = model
        self._client: Any = anthropic.AsyncAnthropic(api_key=api_key)

    async def next_turn(
        self,
        *,
        system_prompt: str,
        conversation: list[ConversationMessage],
        tools: list[ToolDefinition],
    ) -> ProviderTurn:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=_to_anthropic_messages(conversation),
            tools=[
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ],
        )

        tool_calls = tuple(
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
            for block in response.content
            if block.type == "tool_use"
        )
        text_parts = [block.text for block in response.content if block.type == "text"]
        text = "\n".join(text_parts) if text_parts else None

        if tool_calls:
            return ProviderTurn(tool_calls=tool_calls, text=text)
        return ProviderTurn(text=text or "")
