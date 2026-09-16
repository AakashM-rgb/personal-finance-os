"""Natural-language -> app.search.schemas.FinancialSearchQuery.

The deterministic interpreter (`DeterministicSearchInterpreter`) is a
fixed, regex/keyword-based parser - the same "honest about being a fixed
set of recognized shapes, not a general language-understanding system"
philosophy as app.ai.provider.mock_intents and app.services.
quick_add_parser. It runs unconditionally and is what actually executes
whenever no external AI provider is configured (CLAUDE.md: "MockProvider
is used automatically when no API key is configured").

Whatever interpreter runs, its raw output is a plain dict - untrusted until
it passes through FinancialSearchQuery.model_validate() in `interpret()`
below. Neither interpreter ever touches a database session, builds SQL, or
executes anything; the deterministic interpreter does its own text
matching against a `categories` list the caller already fetched through
the normal, authorized category service.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import status
from pydantic import ValidationError

from app.ai.provider.base import ConversationMessage, ToolDefinition
from app.ai.provider.factory import get_ai_provider
from app.core.errors import AppError
from app.models.transaction import TransactionType
from app.schemas.category import CategoryRead
from app.search.category_resolution import CategoryResolution, resolve_category_phrase
from app.search.period_phrases import (
    resolve_month_keyword,
    resolve_relative_period,
)
from app.search.schemas import WEEKEND_DAYS_OF_WEEK, FinancialSearchQuery

_STOPWORDS = frozenset(
    {
        "expense",
        "expenses",
        "spending",
        "spend",
        "spent",
        "purchase",
        "purchases",
        "transaction",
        "transactions",
        "money",
        "payment",
        "payments",
        "bought",
        "buy",
        "cost",
        "costs",
        "on",
        "in",
        "for",
        "the",
        "a",
        "an",
        "of",
        "and",
        "my",
        "show",
        "me",
        "find",
        "search",
        "list",
        "all",
        "with",
    }
)

# Money token: optional currency marker, digits with optional comma
# grouping and decimal, optional trailing "k" shorthand (e.g. "70k").
_AMOUNT_TOKEN = r"(?:₹|rs\.?|inr)?\s*([\d]+(?:,\d{2,3})*(?:\.\d{1,2})?)\s*(k)?\b"
_MIN_PHRASES = r"(?:above|over|more than|at least|greater than|minimum of|minimum)"
_MAX_PHRASES = r"(?:under|below|less than|at most|up to|maximum of|maximum)"
_MIN_AMOUNT_RE = re.compile(rf"\b{_MIN_PHRASES}\s+{_AMOUNT_TOKEN}", re.IGNORECASE)
_MAX_AMOUNT_RE = re.compile(rf"\b{_MAX_PHRASES}\s+{_AMOUNT_TOKEN}", re.IGNORECASE)

_RELATIVE_PERIOD_RE = re.compile(
    r"\b(today|yesterday|this week|last week|this month|last month|this year|last year)\b",
    re.IGNORECASE,
)
_MONTH_NAME_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun[e]?|jul[y]?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)
_WEEKEND_RE = re.compile(r"\bweekends?\b", re.IGNORECASE)
_SUBSCRIPTION_RE = re.compile(r"\bsubscriptions?\b", re.IGNORECASE)
_BIGGEST_RE = re.compile(r"\b(?:biggest|largest|top|highest)\b", re.IGNORECASE)
_SMALLEST_RE = re.compile(r"\b(?:smallest|lowest)\b", re.IGNORECASE)
_INCOME_RE = re.compile(r"\b(?:income|earned|earning|received|salary|credited)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'&-]*")


def _parse_amount_to_minor(raw: str, has_k_suffix: bool) -> int:
    """Converts a money-looking token ("1,234.50", "999", "70k") to integer
    minor units using only string/integer arithmetic - never
    `float(text) * 100`, which can misround an exact rupee value."""
    cleaned = raw.replace(",", "")
    if has_k_suffix:
        return int(cleaned) * 1000 * 100
    if "." in cleaned:
        whole, _, frac = cleaned.partition(".")
        frac = (frac + "00")[:2]
    else:
        whole, frac = cleaned, "00"
    return int(whole) * 100 + int(frac)


@dataclass(frozen=True)
class InterpretationOutcome:
    query: FinancialSearchQuery
    requires_confirmation: bool
    ambiguity_reason: str | None
    ambiguous_categories: list[CategoryRead] = field(default_factory=list)


def _strip_match(text: str, match: re.Match[str]) -> str:
    return text[: match.start()] + " " + text[match.end() :]


def _parse_deterministically(
    query_text: str, *, categories: list[CategoryRead], now: datetime
) -> tuple[dict, CategoryResolution]:
    working = query_text
    fields: dict = {}

    min_match = _MIN_AMOUNT_RE.search(working)
    if min_match:
        fields["min_amount_minor"] = _parse_amount_to_minor(
            min_match.group(1), bool(min_match.group(2))
        )
        working = _strip_match(working, min_match)

    max_match = _MAX_AMOUNT_RE.search(working)
    if max_match:
        fields["max_amount_minor"] = _parse_amount_to_minor(
            max_match.group(1), bool(max_match.group(2))
        )
        working = _strip_match(working, max_match)

    relative_match = _RELATIVE_PERIOD_RE.search(working)
    if relative_match:
        period = resolve_relative_period(relative_match.group(1), now=now)
        working = _strip_match(working, relative_match)
    else:
        period = None
        month_match = _MONTH_NAME_RE.search(working)
        if month_match:
            period = resolve_month_keyword(month_match.group(1), now=now)
            working = _strip_match(working, month_match)

    if period is not None:
        fields["start_date"] = period.start_date
        fields["end_date"] = period.end_date

    weekend_match = _WEEKEND_RE.search(working)
    if weekend_match:
        fields["days_of_week"] = list(WEEKEND_DAYS_OF_WEEK)
        working = _WEEKEND_RE.sub(" ", working)

    if _SUBSCRIPTION_RE.search(working):
        fields["subscriptions_only"] = True
        working = _SUBSCRIPTION_RE.sub(" ", working)

    if _BIGGEST_RE.search(working):
        fields["sort"] = "amount_desc"
        working = _BIGGEST_RE.sub(" ", working)
    elif _SMALLEST_RE.search(working):
        fields["sort"] = "amount_asc"
        working = _SMALLEST_RE.sub(" ", working)

    if _INCOME_RE.search(working):
        fields["transaction_type"] = TransactionType.INCOME
        working = _INCOME_RE.sub(" ", working)
    else:
        fields["transaction_type"] = TransactionType.EXPENSE

    remaining_tokens = [
        token for token in _WORD_RE.findall(working) if token.lower() not in _STOPWORDS
    ]

    category_resolution = CategoryResolution(matched=None)
    if remaining_tokens:
        category_resolution = resolve_category_phrase(" ".join(remaining_tokens), categories)

    if category_resolution.matched is not None:
        fields["category_id"] = category_resolution.matched.id
        matched_name_tokens = {
            tok.lower() for tok in _WORD_RE.findall(category_resolution.matched.name)
        }
        leftover = [t for t in remaining_tokens if t.lower() not in matched_name_tokens]
        if leftover:
            fields["search_text"] = " ".join(leftover)
    elif not category_resolution.ambiguous_candidates and remaining_tokens:
        fields["search_text"] = " ".join(remaining_tokens)

    return fields, category_resolution


def _has_qualifying_signal(query: FinancialSearchQuery) -> bool:
    """Whether the interpretation carries at least one specific "what" (or
    an explicit sort request) beyond a bare date range - a search that is
    ONLY a date range (or has no criteria at all) is too vague to run
    silently, e.g. "August" or "expenses" alone; "biggest expenses this
    year" and "weekend spending" are NOT vague even without a category or
    merchant filter, because they carry an explicit analytical/day-of-week
    signal."""
    return any(
        [
            query.search_text is not None,
            query.category_id is not None,
            query.min_amount_minor is not None,
            query.max_amount_minor is not None,
            query.subscriptions_only,
            query.days_of_week is not None,
            query.sort != "date_desc",
        ]
    )


def _build_outcome(fields: dict, category_resolution: CategoryResolution) -> InterpretationOutcome:
    try:
        query = FinancialSearchQuery.model_validate(fields)
    except ValidationError as exc:
        # Never let a raw pydantic error (or, for the AI-assisted path, a
        # malformed/hallucinated structure) reach the client as a generic
        # 500 - a failed interpretation is a clean, user-actionable 422.
        raise SearchInterpretationError(
            "Couldn't understand that search. Try rephrasing it."
        ) from exc

    if category_resolution.ambiguous_candidates:
        return InterpretationOutcome(
            query=query,
            requires_confirmation=True,
            ambiguity_reason=(
                "Multiple categories could match your search - "
                "choose one, or run the search without a category filter."
            ),
            ambiguous_categories=category_resolution.ambiguous_candidates,
        )

    if not _has_qualifying_signal(query):
        return InterpretationOutcome(
            query=query,
            requires_confirmation=True,
            ambiguity_reason=(
                "This search is quite general - add a merchant, category, "
                "amount, or a more specific request before running it."
            ),
        )

    return InterpretationOutcome(query=query, requires_confirmation=False, ambiguity_reason=None)


class DeterministicSearchInterpreter:
    name = "deterministic"

    async def interpret(
        self, query_text: str, *, categories: list[CategoryRead], now: datetime
    ) -> InterpretationOutcome:
        fields, category_resolution = _parse_deterministically(
            query_text, categories=categories, now=now
        )
        return _build_outcome(fields, category_resolution)


_SEARCH_TOOL_NAME = "interpret_financial_search"
_SEARCH_TOOL_DESCRIPTION = (
    "Extract a structured financial search query from the user's natural-language "
    "request. Only use fields that are clearly implied by the text - never invent a "
    "category, merchant, date, or amount that isn't there. If a category is named, "
    "set category_id to the matching id from the provided category list, or leave it "
    "unset if no category clearly matches."
)


class AnthropicSearchInterpreter:
    """Constrains a real Anthropic model to produce ONLY the same
    FinancialSearchQuery shape the deterministic interpreter produces, via
    a single forced tool call - the model is never asked to execute
    anything, only to propose structured arguments, which are validated
    exactly like any other AI-produced input before use (see
    app.search.interpreter.interpret). Lazily depends on the same
    `anthropic` package app.ai.provider.anthropic_provider uses; this
    class is only ever instantiated when a real provider is configured.
    """

    name = "anthropic"

    def __init__(self) -> None:
        self._provider = get_ai_provider()

    async def interpret(
        self, query_text: str, *, categories: list[CategoryRead], now: datetime
    ) -> InterpretationOutcome:
        category_lines = "\n".join(f"- {c.name} (id: {c.id})" for c in categories) or "(none)"
        system_prompt = (
            "You convert a personal-finance search phrase into a structured query by "
            f"calling {_SEARCH_TOOL_NAME} exactly once. Today's date is "
            f"{now.date().isoformat()}. The user's categories are:\n{category_lines}"
        )
        tool = ToolDefinition(
            name=_SEARCH_TOOL_NAME,
            description=_SEARCH_TOOL_DESCRIPTION,
            input_schema=FinancialSearchQuery.model_json_schema(),
        )
        conversation = [ConversationMessage(role="user", text=query_text)]

        try:
            turn = await self._provider.next_turn(
                system_prompt=system_prompt, conversation=conversation, tools=[tool]
            )
        except Exception as exc:  # noqa: BLE001 - a provider failure must never crash a search
            raise SearchInterpretationError("The search assistant is unavailable.") from exc

        call = next((c for c in turn.tool_calls if c.name == _SEARCH_TOOL_NAME), None)
        if call is None:
            # The model answered in plain text instead of calling the tool -
            # never treated as a query; the caller falls back to the
            # deterministic interpreter.
            raise SearchInterpretationError("Could not extract a structured search from that text.")

        fields = dict(call.arguments)
        if not fields.get("transaction_type"):
            # Same default the deterministic interpreter applies (see
            # _parse_deterministically) - an unset type must never fall
            # through to FinancialSearchQuery's own `None` (which the query
            # builder maps to "no type filter" and would silently let
            # transfers leak into a search result set). Only an explicit,
            # AI-recognized "income"/"transfer" mention should override this.
            fields["transaction_type"] = TransactionType.EXPENSE
        category_resolution = CategoryResolution(matched=None)
        category_id = fields.get("category_id")
        if category_id is not None:
            matched = next((c for c in categories if str(c.id) == str(category_id)), None)
            if matched is None:
                # The model referenced a category id we never offered it -
                # never trust it; drop the field rather than look it up
                # blindly (there is no "look up any category by id" path
                # here - only the ids explicitly listed above are valid).
                fields = {k: v for k, v in fields.items() if k != "category_id"}
            else:
                category_resolution = CategoryResolution(matched=matched)

        return _build_outcome(fields, category_resolution)


class SearchInterpretationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "search_interpretation_failed"


def get_search_interpreter(
    *, ai_enabled: bool = True
) -> "DeterministicSearchInterpreter | AnthropicSearchInterpreter":
    """Mirrors the selection pattern in app.ai.provider.factory /
    app.ocr.factory / app.storage.factory: a real provider only when
    actually configured, the deterministic implementation otherwise -
    never a silent pretend call to an external service.

    `ai_enabled` is the caller's authenticated user's own per-user AI
    setting (CLAUDE.md §14: "the tool layer itself must refuse ... not
    just hide the chat UI"). When it's off, the AI-assisted interpreter is
    never selected regardless of provider configuration - the deterministic
    interpreter runs instead, so search still works, it just never sends
    this user's query text or category names to an external AI provider.
    """
    provider = get_ai_provider()
    if provider.name == "anthropic" and ai_enabled:
        return AnthropicSearchInterpreter()
    return DeterministicSearchInterpreter()


async def interpret(
    query_text: str,
    *,
    categories: list[CategoryRead],
    now: datetime | None = None,
    ai_enabled: bool = True,
) -> InterpretationOutcome:
    """The single entry point app.search.service calls. Always falls back
    to the deterministic interpreter if an AI-assisted attempt fails or
    produces something that doesn't validate - a search must never simply
    error out just because an optional AI provider had a bad response."""
    resolved_now = now or datetime.now(UTC)
    interpreter = get_search_interpreter(ai_enabled=ai_enabled)

    if isinstance(interpreter, DeterministicSearchInterpreter):
        return await interpreter.interpret(query_text, categories=categories, now=resolved_now)

    try:
        return await interpreter.interpret(query_text, categories=categories, now=resolved_now)
    except Exception:  # noqa: BLE001 - any AI-assisted failure falls back, never errors out
        fallback = DeterministicSearchInterpreter()
        return await fallback.interpret(query_text, categories=categories, now=resolved_now)


__all__ = [
    "AnthropicSearchInterpreter",
    "DeterministicSearchInterpreter",
    "InterpretationOutcome",
    "SearchInterpretationError",
    "get_search_interpreter",
    "interpret",
]
