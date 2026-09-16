"""The one validated internal query structure a natural-language
interpretation is ever allowed to produce, plus the search API's
request/response schemas.

`FinancialSearchQuery` has `extra="forbid"`: any field an interpreter
(deterministic or AI-assisted) invents beyond this explicit set is rejected
by Pydantic before it ever reaches app.search.query_builder. There is no
generic {field, operator, value} filter here on purpose - see
app.search.__init__ for the full architecture note.
"""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.tools.schemas import TransactionSummary
from app.models.transaction import TransactionType

MAX_RESULT_LIMIT = 100
DEFAULT_RESULT_LIMIT = 20
MAX_QUERY_TEXT_LENGTH = 200
# A resolved date range wider than this would be an unbounded query - same
# reasoning as app.ai.tools.period_resolution.MAX_CUSTOM_RANGE_DAYS.
MAX_DATE_RANGE_DAYS = 1830  # ~5 years

SortOption = Literal["date_desc", "date_asc", "amount_desc", "amount_asc"]

# Postgres EXTRACT(DOW FROM ...) convention: 0=Sunday, 6=Saturday.
WEEKEND_DAYS_OF_WEEK = (0, 6)


class FinancialSearchQuery(BaseModel):
    """The ONLY structure a natural-language interpretation may produce."""

    model_config = ConfigDict(extra="forbid")

    search_text: str | None = Field(default=None, max_length=MAX_QUERY_TEXT_LENGTH)
    category_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_amount_minor: int | None = Field(default=None, ge=0)
    max_amount_minor: int | None = Field(default=None, ge=0)
    transaction_type: TransactionType | None = None
    days_of_week: list[int] | None = None
    subscriptions_only: bool = False
    sort: SortOption = "date_desc"
    limit: int = Field(default=DEFAULT_RESULT_LIMIT, ge=1, le=MAX_RESULT_LIMIT)

    @model_validator(mode="after")
    def _check(self) -> "FinancialSearchQuery":
        if (
            self.min_amount_minor is not None
            and self.max_amount_minor is not None
            and self.min_amount_minor > self.max_amount_minor
        ):
            raise ValueError("min_amount_minor must not exceed max_amount_minor.")

        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("start_date must not be after end_date.")
            if (self.end_date - self.start_date).days > MAX_DATE_RANGE_DAYS:
                raise ValueError(
                    f"A search date range can span at most {MAX_DATE_RANGE_DAYS} days."
                )

        if self.days_of_week is not None:
            if not self.days_of_week:
                raise ValueError("days_of_week must not be empty when provided.")
            if any(day < 0 or day > 6 for day in self.days_of_week):
                raise ValueError("days_of_week values must be 0-6 (Sunday-Saturday).")
            if len(set(self.days_of_week)) != len(self.days_of_week):
                raise ValueError("days_of_week must not contain duplicates.")

        return self


class CategoryCandidate(BaseModel):
    id: uuid.UUID
    name: str
    icon: str


class InterpretedCriteria(BaseModel):
    """A human-readable rendering of the resolved query - always returned,
    so the frontend can show exactly what will run (or would have run)
    before executing."""

    search_text: str | None
    category_name: str | None
    start_date: date | None
    end_date: date | None
    min_amount_minor: int | None
    max_amount_minor: int | None
    transaction_type: TransactionType | None
    is_weekend_only: bool
    subscriptions_only: bool
    sort: SortOption
    limit: int
    currency: str


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=MAX_QUERY_TEXT_LENGTH)
    # Set by the frontend on a second submission, after the user has
    # reviewed an ambiguous interpretation and asked to run it anyway.
    confirmed: bool = False
    # An explicit category the user picked from a prior response's
    # `ambiguous_categories` - bypasses text-based category resolution
    # entirely. Ownership/visibility is still enforced by the repository
    # before use, exactly like any other user-supplied id in this app.
    category_override_id: uuid.UUID | None = None


class SearchResponse(BaseModel):
    interpretation: InterpretedCriteria
    requires_confirmation: bool
    ambiguity_reason: str | None
    ambiguous_categories: list[CategoryCandidate]
    results: list[TransactionSummary]
    result_count: int
    total_matching: int
    limited: bool
    provider: str
