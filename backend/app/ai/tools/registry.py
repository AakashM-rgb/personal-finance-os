"""The single choke point every AI tool call is validated and executed
through. Nothing in app.ai.provider ever calls an executor directly - this
module is the only caller of app.ai.tools.executors, and it never trusts
anything about a proposed tool call except its name and its (validated)
arguments.

Security invariants enforced here:
- The tool name must be one of the exact eight in app.ai.tools.catalog -
  anything else is rejected before any code related to it runs.
- Arguments are parsed through that tool's own Pydantic model
  (`extra="forbid"`) - an unrecognized field, a malformed date, an
  out-of-range limit, or an invalid enum value is rejected by pydantic
  itself, never partially accepted.
- `user_id` is NEVER read from the AI-supplied arguments - it is a
  required keyword of this function, always the authenticated caller's own
  id from the request context. If the AI-supplied arguments happen to
  contain a user-identity-shaped key at all, that is rejected outright
  (see _REJECTED_ARGUMENT_KEYS) rather than silently ignored, so an
  attempt to override identity is visible in the rejection log, not
  swallowed - even though no tool's Args model declares such a field
  anyway, so `extra="forbid"` would already catch it.
- Every accepted or rejected call is logged with safe, structured metadata
  only (tool name, success, error category, duration) - never the full
  argument or result payload, which could contain the user's financial
  figures.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.catalog import TOOL_NAMES, get_tool_spec

logger = logging.getLogger("app.ai.tools")

_REJECTED_ARGUMENT_KEYS = frozenset({"user_id", "userId", "user", "owner_id", "account_owner"})


@dataclass(frozen=True)
class ToolCallResult:
    tool_name: str
    ok: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: float = 0.0


def _reject(
    *, tool_name: str, user_id: uuid.UUID, error_code: str, error_message: str, started: float
) -> ToolCallResult:
    duration_ms = (time.perf_counter() - started) * 1000
    logger.warning(
        "ai_tool_call_rejected",
        extra={
            "user_id": str(user_id),
            "tool_name": tool_name,
            "error_code": error_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return ToolCallResult(
        tool_name=tool_name,
        ok=False,
        error_code=error_code,
        error_message=error_message,
        duration_ms=duration_ms,
    )


async def validate_and_execute(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ai_enabled: bool,
    tool_name: str,
    raw_arguments: dict[str, Any] | None,
) -> ToolCallResult:
    """The only function allowed to call a tool executor. `ai_enabled` is
    supplied by the caller (app.services.ai_assistant_service), which reads
    it fresh from the user's own settings for every request - the tool
    layer never assumes access is allowed."""
    started = time.perf_counter()
    raw_arguments = raw_arguments or {}

    if not ai_enabled:
        return _reject(
            tool_name=tool_name,
            user_id=user_id,
            error_code="ai_disabled",
            error_message="AI access to financial data is disabled for this account.",
            started=started,
        )

    if tool_name not in TOOL_NAMES:
        return _reject(
            tool_name=tool_name,
            user_id=user_id,
            error_code="unknown_tool",
            error_message=f"{tool_name!r} is not an available tool.",
            started=started,
        )

    if _REJECTED_ARGUMENT_KEYS.intersection(raw_arguments):
        return _reject(
            tool_name=tool_name,
            user_id=user_id,
            error_code="identity_override_attempt",
            error_message="Tool arguments may not specify a user identity.",
            started=started,
        )

    spec = get_tool_spec(tool_name)
    assert spec is not None  # guaranteed by the TOOL_NAMES membership check above

    try:
        parsed_args = spec.args_model.model_validate(raw_arguments)
    except ValidationError:
        return _reject(
            tool_name=tool_name,
            user_id=user_id,
            error_code="invalid_arguments",
            error_message="One or more arguments were invalid.",
            started=started,
        )

    try:
        result: BaseModel = await spec.executor(db, user_id=user_id, args=parsed_args)
    except ValueError as exc:
        # Raised by pure helpers like app.ai.tools.period_resolution for a
        # semantically invalid but well-typed argument (e.g. an out-of-range
        # custom date range) - a validation failure, not a server fault.
        return _reject(
            tool_name=tool_name,
            user_id=user_id,
            error_code="invalid_arguments",
            error_message=str(exc),
            started=started,
        )
    except Exception:  # noqa: BLE001 - a tool failure must never crash the assistant turn
        duration_ms = (time.perf_counter() - started) * 1000
        logger.error(
            "ai_tool_call_failed",
            extra={
                "user_id": str(user_id),
                "tool_name": tool_name,
                "duration_ms": round(duration_ms, 2),
            },
            exc_info=True,
        )
        return ToolCallResult(
            tool_name=tool_name,
            ok=False,
            error_code="execution_error",
            error_message="This tool could not complete the request.",
            duration_ms=duration_ms,
        )

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "ai_tool_call_succeeded",
        extra={
            "user_id": str(user_id),
            "tool_name": tool_name,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return ToolCallResult(
        tool_name=tool_name, ok=True, data=result.model_dump(mode="json"), duration_ms=duration_ms
    )
