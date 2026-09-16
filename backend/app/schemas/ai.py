"""Financial AI Assistant request/response schemas.

`AssistantRequest.history` is the frontend's own local session history
(this backend is stateless across requests - see
app.services.ai_assistant_service) - it is always plain display text, never
trusted as instructions, and bounded in both length and count so a request
body can't grow unbounded.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DISCLAIMER = (
    "This is not licensed financial advice. Figures are based only on your own recorded "
    "data and, where noted, general guidelines - not a guarantee of any outcome."
)

_MAX_MESSAGE_LENGTH = 2000
_MAX_HISTORY_MESSAGES = 20


class AssistantMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=_MAX_MESSAGE_LENGTH)


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=_MAX_MESSAGE_LENGTH)
    history: list[AssistantMessageInput] = Field(
        default_factory=list, max_length=_MAX_HISTORY_MESSAGES
    )


class ToolUsage(BaseModel):
    tool_name: str
    ok: bool


class AssistantResponse(BaseModel):
    answer: str
    tools_used: list[ToolUsage]
    provider: str
    disclaimer: str
