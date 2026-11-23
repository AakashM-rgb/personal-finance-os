"""The single definition of what a money field may contain.

Every money value in this app is an integer count of minor units (paise) --
never a float (CLAUDE.md §13). Lower bounds were always enforced per field,
but Python's `int` has no ceiling and PostgreSQL's `BIGINT` does, so an
unbounded request body could carry a value that either overflows the column
on insert (a driver error surfacing as a 500) or stores a figure that quietly
poisons every aggregate it reaches: net worth, the health score, budget
percentages, credit utilization.

`MAX_MONEY_MINOR` caps a single submitted value at 10^13 paise
(Rs 1,00,00,00,00,000 -- a hundred billion rupees). That is far above any
personal balance the product targets, and still about 9x10^5 times smaller
than `BIGINT`'s maximum, so sums across very many rows stay exact instead of
overflowing. Negative values are only meaningful for a stored balance (a
credit-card credit balance, see docs/DATABASE.md), which is why the signed
bound is separate rather than applied everywhere.

Use these aliases for request schemas. Response schemas stay plain `int`:
they report what the service computed, and a bound there would turn a
calculation bug into a serialization error instead of a visible number.
"""

from typing import Annotated

from pydantic import Field

MAX_MONEY_MINOR = 10**13

#: An amount that must be strictly positive: a transaction, a budget, a
#: credit limit. Zero is rejected -- "no amount" is None, not 0.
PositiveMoneyMinor = Annotated[int, Field(gt=0, le=MAX_MONEY_MINOR)]

#: An amount where zero is meaningful: a goal's starting balance, a receipt
#: line total, a minimum payment of nothing.
NonNegativeMoneyMinor = Annotated[int, Field(ge=0, le=MAX_MONEY_MINOR)]

#: A stored account balance, which may legitimately be negative: an
#: overdrawn bank account, or a credit card the user has overpaid.
SignedMoneyMinor = Annotated[int, Field(ge=-MAX_MONEY_MINOR, le=MAX_MONEY_MINOR)]
