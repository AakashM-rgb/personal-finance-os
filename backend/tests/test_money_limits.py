"""Every money value arriving from a client must be bounded on both sides.

F-006: money fields had lower bounds but no ceiling. Python's `int` is
unbounded and `BIGINT` is not, so a request could either overflow the column
(a 500 from the driver) or store a figure that silently poisons net worth, the
health score, budget percentages and credit utilization. The structural test
below is the one that matters long-term: it fails if any new request field
ending in `_minor` is added without a ceiling.
"""

import importlib
import inspect
import pkgutil
from typing import Any, get_args

import pytest
from annotated_types import Ge, Gt, Le
from httpx import AsyncClient
from pydantic import BaseModel
from pydantic.fields import FieldInfo

import app.schemas
from app.schemas.money import MAX_MONEY_MINOR

# Request models: what a client can send. Response models report what the
# service computed and stay unbounded on purpose -- a ceiling there would turn
# a calculation bug into a serialization error instead of a visible number.
_REQUEST_SUFFIXES = ("Create", "Update", "Confirm", "Fields", "Request")


def _request_models() -> list[type[BaseModel]]:
    models: list[type[BaseModel]] = []
    for module_info in pkgutil.iter_modules(app.schemas.__path__):
        module = importlib.import_module(f"app.schemas.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == module.__name__
                and obj.__name__.endswith(_REQUEST_SUFFIXES)
            ):
                models.append(obj)
    return models


def _money_fields(model: type[BaseModel]) -> list[str]:
    return [name for name in model.model_fields if name.endswith("_minor")]


def _constraints(field: FieldInfo) -> list[Any]:
    """Every annotated_types constraint on a field, wherever Pydantic put it.

    A required field keeps them on FieldInfo.metadata, but an optional one
    (`PositiveMoneyMinor | None`) nests them inside the union member's own
    Annotated metadata, so a top-level read would see nothing at all and make
    this whole check pass vacuously.
    """
    found: list[Any] = list(field.metadata)
    stack: list[Any] = [field.annotation]
    while stack:
        current = stack.pop()
        for extra in getattr(current, "__metadata__", ()):
            nested = getattr(extra, "metadata", None)
            found.extend(nested if nested else [extra])
        stack.extend(get_args(current))
    return found


def test_request_models_were_actually_discovered() -> None:
    """Guards the guard: a broken discovery rule would make every assertion
    below vacuous."""
    models = _request_models()
    names = {model.__name__ for model in models}
    assert {"TransactionCreate", "AccountCreate", "BudgetItemCreate"} <= names
    assert sum(len(_money_fields(model)) for model in models) >= 15


@pytest.mark.parametrize("model", _request_models(), ids=lambda m: m.__name__)
def test_every_money_request_field_has_an_upper_bound(model: type[BaseModel]) -> None:
    for name in _money_fields(model):
        constraints = _constraints(model.model_fields[name])
        uppers = [c for c in constraints if isinstance(c, Le)]
        lowers = [c for c in constraints if isinstance(c, (Gt, Ge))]
        assert uppers, f"{model.__name__}.{name} has no upper bound (see app.schemas.money)"
        assert lowers, f"{model.__name__}.{name} has no lower bound"
        assert uppers[0].le == MAX_MONEY_MINOR, (
            f"{model.__name__}.{name} uses its own ceiling instead of MAX_MONEY_MINOR"
        )


async def _account(client: AsyncClient, headers: dict, **payload: object) -> dict:
    payload.setdefault("name", "Account")
    payload.setdefault("type", "bank_account")
    payload.setdefault("balance_minor", 100_000)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_a_transaction_above_the_ceiling_is_rejected_not_stored(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _account(client, auth_headers)
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": MAX_MONEY_MINOR + 1,
        },
    )
    assert response.status_code == 422, response.text

    listed = await client.get("/api/v1/transactions", headers=auth_headers)
    assert listed.json()["data"] == []


async def test_a_value_that_would_overflow_bigint_is_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _account(client, auth_headers)
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 2**70,
        },
    )
    assert response.status_code == 422, response.text


async def test_the_ceiling_itself_is_accepted(client: AsyncClient, auth_headers: dict) -> None:
    """The bound has to be generous enough not to reject real money."""
    account = await _account(client, auth_headers, balance_minor=0)
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": account["id"],
            "type": "income",
            "amount_minor": MAX_MONEY_MINOR,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["amount_minor"] == MAX_MONEY_MINOR


async def test_an_account_balance_is_bounded_in_both_directions(
    client: AsyncClient, auth_headers: dict
) -> None:
    """A balance may be negative -- an overdrawn account, or a card the user has
    overpaid -- so it needs a floor as well as a ceiling."""
    too_high = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "A", "type": "bank_account", "balance_minor": MAX_MONEY_MINOR + 1},
    )
    assert too_high.status_code == 422, too_high.text

    too_low = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "A", "type": "bank_account", "balance_minor": -MAX_MONEY_MINOR - 1},
    )
    assert too_low.status_code == 422, too_low.text

    allowed = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "A", "type": "bank_account", "balance_minor": -5_000_00},
    )
    assert allowed.status_code == 201, allowed.text


async def test_a_credit_limit_above_the_ceiling_is_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "Card",
            "type": "credit_card",
            "balance_minor": 0,
            "credit_card": {
                "credit_limit_minor": MAX_MONEY_MINOR + 1,
                "statement_day": 5,
                "payment_due_day": 20,
            },
        },
    )
    assert response.status_code == 422, response.text


async def test_a_savings_goal_target_above_the_ceiling_is_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Goal",
            "target_amount_minor": MAX_MONEY_MINOR + 1,
            "target_date": "2030-01-01",
        },
    )
    assert response.status_code == 422, response.text
