from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import recurring_transaction_generator
from app.models.recurring_transaction import RecurrenceFrequency
from app.services.recurrence import next_occurrence_date


def _expected_occurrences(
    start: date, frequency: RecurrenceFrequency, day_of_month: int, today: date
) -> list[date]:
    """Independently recomputes the full expected occurrence list using the
    same pure function the service relies on - lets a generation test
    assert against dynamically-correct dates instead of brittle hardcoded
    calendar literals, while still genuinely exercising month-end/leap-year
    handling through the real API and database."""
    if start > today:
        return []
    occurrences = [start]
    current = start
    while True:
        current = next_occurrence_date(current, frequency, day_of_month=day_of_month)
        if current > today:
            break
        occurrences.append(current)
    return occurrences


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Test Account")
    payload.setdefault("type", "cash")
    payload.setdefault("balance_minor", 10000000)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


async def _create_recurring(
    client: AsyncClient, headers: dict, account_id: str, **overrides
) -> dict:
    payload = {
        "name": "Netflix",
        "account_id": account_id,
        "type": "expense",
        "amount_minor": 64900,
        "frequency": "monthly",
        "start_date": date.today().isoformat(),
    }
    payload.update(overrides)
    response = await client.post("/api/v1/recurring-transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _generate(client: AsyncClient, headers: dict) -> list[dict]:
    response = await client.post("/api/v1/recurring-transactions/generate", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# --- creation / validation ----------------------------------------------------------


async def test_create_recurring_expense(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    today = date.today()

    recurring = await _create_recurring(
        client,
        auth_headers,
        account["id"],
        name="Netflix",
        type="expense",
        amount_minor=64900,
        category_id=food_id,
        frequency="monthly",
        start_date=today.isoformat(),
    )

    assert recurring["name"] == "Netflix"
    assert recurring["account_id"] == account["id"]
    assert recurring["account_name"] == account["name"]
    assert recurring["category_id"] == food_id
    assert recurring["category_name"] == "Food"
    assert recurring["type"] == "expense"
    assert recurring["amount_minor"] == 64900
    assert recurring["currency"] == account["currency"]
    assert recurring["frequency"] == "monthly"
    assert recurring["start_date"] == today.isoformat()
    assert recurring["next_occurrence_date"] == today.isoformat()  # nothing generated yet
    assert recurring["is_active"] is True


async def test_create_recurring_income_without_category(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    recurring = await _create_recurring(
        client, auth_headers, account["id"], name="Salary", type="income", amount_minor=5000000
    )
    assert recurring["type"] == "income"
    assert recurring["category_id"] is None
    assert recurring["category_name"] is None


async def test_create_rejects_transfer_type(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "type": "transfer",
            "amount_minor": 1000,
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_zero_or_negative_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    for bad_amount in [0, -500]:
        response = await client.post(
            "/api/v1/recurring-transactions",
            headers=auth_headers,
            json={
                "name": "Bad",
                "account_id": account["id"],
                "type": "expense",
                "amount_minor": bad_amount,
                "frequency": "monthly",
                "start_date": date.today().isoformat(),
            },
        )
        assert response.status_code == 422


async def test_create_rejects_unknown_account(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": "00000000-0000-0000-0000-00000000ffff",
            "type": "expense",
            "amount_minor": 1000,
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 404


async def test_create_rejects_archived_account(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    archive_response = await client.delete(
        f"/api/v1/accounts/{account['id']}", headers=auth_headers
    )
    assert archive_response.status_code == 200

    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 1000,
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_unknown_category(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 1000,
            "category_id": "00000000-0000-0000-0000-00000000ffff",
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_another_users_custom_category(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    their_category_response = await client.post(
        "/api/v1/categories",
        headers=other_auth_headers,
        json={"name": "Their Category", "icon": "🏷️", "color": "#123456"},
    )
    assert their_category_response.status_code == 201
    their_category = their_category_response.json()["data"]

    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 1000,
            "category_id": their_category["id"],
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_unknown_fields(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 1000,
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
            "user_id": "00000000-0000-0000-0000-00000000ffff",
        },
    )
    assert response.status_code == 422


# --- CRUD -----------------------------------------------------------------------------


async def test_list_starts_empty(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/recurring-transactions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_get_by_id(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _create_recurring(client, auth_headers, account["id"])
    response = await client.get(
        f"/api/v1/recurring-transactions/{created['id']}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


async def test_get_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(
        "/api/v1/recurring-transactions/00000000-0000-0000-0000-00000000ffff",
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_update_amount_and_frequency(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _create_recurring(client, auth_headers, account["id"], frequency="monthly")
    response = await client.put(
        f"/api/v1/recurring-transactions/{created['id']}",
        headers=auth_headers,
        json={"amount_minor": 99900, "frequency": "weekly"},
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["amount_minor"] == 99900
    assert updated["frequency"] == "weekly"
    assert updated["name"] == created["name"]


async def test_update_category_clear(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    created = await _create_recurring(client, auth_headers, account["id"], category_id=food_id)
    response = await client.put(
        f"/api/v1/recurring-transactions/{created['id']}",
        headers=auth_headers,
        json={"clear_category": True},
    )
    assert response.status_code == 200
    assert response.json()["data"]["category_id"] is None


async def test_update_account_changes_currency(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers, currency="INR")
    other_account = await _create_account(client, auth_headers, name="USD Account", currency="USD")
    created = await _create_recurring(client, auth_headers, account["id"])

    response = await client.put(
        f"/api/v1/recurring-transactions/{created['id']}",
        headers=auth_headers,
        json={"account_id": other_account["id"]},
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["account_id"] == other_account["id"]
    assert updated["currency"] == "USD"


async def test_update_rejects_transfer_type(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _create_recurring(client, auth_headers, account["id"])
    response = await client.put(
        f"/api/v1/recurring-transactions/{created['id']}",
        headers=auth_headers,
        json={"type": "transfer"},
    )
    assert response.status_code == 422


async def test_update_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.put(
        "/api/v1/recurring-transactions/00000000-0000-0000-0000-00000000ffff",
        headers=auth_headers,
        json={"name": "Nope"},
    )
    assert response.status_code == 404


async def test_deactivate(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _create_recurring(client, auth_headers, account["id"])

    response = await client.delete(
        f"/api/v1/recurring-transactions/{created['id']}", headers=auth_headers
    )
    assert response.status_code == 200

    follow_up = await client.get(
        f"/api/v1/recurring-transactions/{created['id']}", headers=auth_headers
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["data"]["is_active"] is False


async def test_deactivate_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.delete(
        "/api/v1/recurring-transactions/00000000-0000-0000-0000-00000000ffff",
        headers=auth_headers,
    )
    assert response.status_code == 404


# --- authorization isolation --------------------------------------------------------


async def test_cannot_read_another_users_recurring_transaction(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    theirs = await _create_recurring(client, other_auth_headers, their_account["id"])
    response = await client.get(
        f"/api/v1/recurring-transactions/{theirs['id']}", headers=auth_headers
    )
    assert response.status_code == 404


async def test_cannot_update_another_users_recurring_transaction(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    theirs = await _create_recurring(client, other_auth_headers, their_account["id"])
    response = await client.put(
        f"/api/v1/recurring-transactions/{theirs['id']}",
        headers=auth_headers,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


async def test_cannot_deactivate_another_users_recurring_transaction(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    theirs = await _create_recurring(client, other_auth_headers, their_account["id"])

    response = await client.delete(
        f"/api/v1/recurring-transactions/{theirs['id']}", headers=auth_headers
    )
    assert response.status_code == 404

    still_theirs = await client.get(
        f"/api/v1/recurring-transactions/{theirs['id']}", headers=other_auth_headers
    )
    assert still_theirs.json()["data"]["is_active"] is True


async def test_list_never_leaks_another_users_recurring_transactions(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    await _create_recurring(client, other_auth_headers, their_account["id"], name="Theirs")
    account = await _create_account(client, auth_headers)
    await _create_recurring(client, auth_headers, account["id"], name="Mine")

    response = await client.get("/api/v1/recurring-transactions", headers=auth_headers)
    names = [r["name"] for r in response.json()["data"]]
    assert names == ["Mine"]


async def test_generate_only_affects_the_calling_users_schedules(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    my_account = await _create_account(client, auth_headers)
    their_account = await _create_account(client, other_auth_headers)
    past_start = (date.today() - timedelta(days=2)).isoformat()

    await _create_recurring(
        client, auth_headers, my_account["id"], frequency="daily", start_date=past_start
    )
    await _create_recurring(
        client, other_auth_headers, their_account["id"], frequency="daily", start_date=past_start
    )

    generated = await _generate(client, auth_headers)
    assert len(generated) == 3  # today, today-1, today-2

    their_list = await client.get("/api/v1/recurring-transactions", headers=other_auth_headers)
    their_next = their_list.json()["data"][0]["next_occurrence_date"]
    assert their_next == past_start  # untouched by my generate call


# --- generation: edge cases and idempotency -----------------------------------------


async def test_generate_with_start_date_today(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today()
    recurring = await _create_recurring(
        client, auth_headers, account["id"], frequency="daily", start_date=today.isoformat()
    )

    generated = await _generate(client, auth_headers)
    assert len(generated) == 1
    txn = generated[0]
    assert txn["occurred_at"][:10] == today.isoformat()
    assert txn["account_id"] == account["id"]
    assert txn["amount_minor"] == recurring["amount_minor"]
    assert txn["type"] == recurring["type"]
    assert txn["currency"] == recurring["currency"]
    assert txn["recurring_transaction_id"] == recurring["id"]
    assert txn["description"] == recurring["name"]

    after = await client.get(
        f"/api/v1/recurring-transactions/{recurring['id']}", headers=auth_headers
    )
    assert after.json()["data"]["next_occurrence_date"] == (today + timedelta(days=1)).isoformat()


async def test_generate_with_future_start_date_generates_nothing(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    future = date.today() + timedelta(days=10)
    recurring = await _create_recurring(
        client, auth_headers, account["id"], frequency="daily", start_date=future.isoformat()
    )

    generated = await _generate(client, auth_headers)
    assert generated == []

    after = await client.get(
        f"/api/v1/recurring-transactions/{recurring['id']}", headers=auth_headers
    )
    assert after.json()["data"]["next_occurrence_date"] == future.isoformat()


async def test_generate_backfills_a_past_start_date_daily(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    start = date.today() - timedelta(days=5)
    await _create_recurring(
        client, auth_headers, account["id"], frequency="daily", start_date=start.isoformat()
    )

    generated = await _generate(client, auth_headers)
    assert len(generated) == 6  # start..today inclusive
    dates = sorted(txn["occurred_at"][:10] for txn in generated)
    expected = [(start + timedelta(days=i)).isoformat() for i in range(6)]
    assert dates == expected


async def test_generate_weekly(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    start = date.today() - timedelta(days=21)
    await _create_recurring(
        client, auth_headers, account["id"], frequency="weekly", start_date=start.isoformat()
    )

    generated = await _generate(client, auth_headers)
    dates = sorted(txn["occurred_at"][:10] for txn in generated)
    expected = [(start + timedelta(weeks=i)).isoformat() for i in range(4)]
    assert dates == expected


async def test_generate_quarterly(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today()
    start = today - timedelta(days=200)  # spans at least two quarterly steps
    await _create_recurring(
        client, auth_headers, account["id"], frequency="quarterly", start_date=start.isoformat()
    )

    expected = _expected_occurrences(start, RecurrenceFrequency.QUARTERLY, start.day, today)
    generated = await _generate(client, auth_headers)
    dates = sorted(txn["occurred_at"][:10] for txn in generated)
    assert dates == [d.isoformat() for d in expected]
    assert len(expected) >= 2


async def test_generate_monthly_month_end_matches_pure_calculation(
    client: AsyncClient, auth_headers: dict
) -> None:
    # A fixed, safely-past January 31st - guarantees at least one clamped
    # February occurrence in the backfill, regardless of when this test runs.
    start = date(2024, 1, 31)
    today = date.today()
    account = await _create_account(client, auth_headers)
    await _create_recurring(
        client, auth_headers, account["id"], frequency="monthly", start_date=start.isoformat()
    )

    expected = _expected_occurrences(start, RecurrenceFrequency.MONTHLY, 31, today)
    generated = await _generate(client, auth_headers)
    dates = sorted(txn["occurred_at"][:10] for txn in generated)
    assert dates == [d.isoformat() for d in expected]
    assert any(d.month == 2 for d in expected)  # actually exercised a February clamp


async def test_generate_yearly_leap_year_matches_pure_calculation(
    client: AsyncClient, auth_headers: dict
) -> None:
    # A fixed, safely-past leap day - guarantees at least one non-leap-year
    # Feb 28 clamp in the backfill, regardless of when this test runs.
    start = date(2024, 2, 29)
    today = date.today()
    account = await _create_account(client, auth_headers)
    await _create_recurring(
        client, auth_headers, account["id"], frequency="yearly", start_date=start.isoformat()
    )

    expected = _expected_occurrences(start, RecurrenceFrequency.YEARLY, 29, today)
    generated = await _generate(client, auth_headers)
    dates = sorted(txn["occurred_at"][:10] for txn in generated)
    assert dates == [d.isoformat() for d in expected]
    assert len(expected) >= 2  # actually spans at least one full year


async def test_generate_skips_deactivated_recurring_transactions(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    start = date.today() - timedelta(days=10)
    created = await _create_recurring(
        client, auth_headers, account["id"], frequency="daily", start_date=start.isoformat()
    )
    deactivate_response = await client.delete(
        f"/api/v1/recurring-transactions/{created['id']}", headers=auth_headers
    )
    assert deactivate_response.status_code == 200

    generated = await _generate(client, auth_headers)
    assert generated == []


async def test_generate_twice_produces_no_duplicates(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    start = date.today() - timedelta(days=3)
    await _create_recurring(
        client, auth_headers, account["id"], frequency="daily", start_date=start.isoformat()
    )

    first = await _generate(client, auth_headers)
    assert len(first) == 4  # start..today inclusive

    second = await _generate(client, auth_headers)
    assert second == []  # nothing new due - idempotent

    all_transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    linked = [
        t for t in all_transactions.json()["data"] if t["recurring_transaction_id"] is not None
    ]
    assert len(linked) == 4  # not 8 - the second call created nothing new


async def test_generate_repeatedly_stays_idempotent_across_many_calls(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    start = date.today()
    await _create_recurring(
        client, auth_headers, account["id"], frequency="daily", start_date=start.isoformat()
    )

    first = await _generate(client, auth_headers)
    assert len(first) == 1
    for _ in range(3):
        assert await _generate(client, auth_headers) == []

    all_transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    linked = [
        t for t in all_transactions.json()["data"] if t["recurring_transaction_id"] is not None
    ]
    assert len(linked) == 1


async def test_concurrent_generate_hits_db_backstop_without_500(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    """Regression test: two "generate" calls racing to materialize the same
    (recurring_transaction_id, occurred_at) occurrence used to surface as an
    unhandled 500 - the DB's uq_transactions_recurring_occurrence constraint
    correctly stopped the duplicate row, but the IntegrityError it raised
    was only ever caught for the sibling idempotency-key race, not this one,
    so it propagated as a raw internal_error instead of a clean, idempotent
    response. Calling transaction_service.create_transaction directly twice
    for the exact same occurrence reproduces that race deterministically
    (no thread timing needed) against the real unique constraint."""
    import uuid as uuid_module

    from app.schemas.transaction import TransactionCreate
    from app.services import transaction_service

    account = await _create_account(client, auth_headers)
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = uuid_module.UUID(me.json()["data"]["id"])
    recurring = await _create_recurring(client, auth_headers, account["id"], frequency="daily")
    recurring_id = uuid_module.UUID(recurring["id"])

    occurrence = TransactionCreate(
        account_id=uuid_module.UUID(account["id"]),
        type="expense",
        amount_minor=64900,
        occurred_at=date.today().isoformat() + "T00:00:00Z",  # type: ignore[arg-type]
    )

    first = await transaction_service.create_transaction(
        db_session,
        user_id=user_id,
        data=occurrence,
        idempotency_key=None,
        recurring_transaction_id=recurring_id,
    )
    await db_session.commit()

    # Simulates the losing side of a concurrent "generate" call landing on
    # the exact same occurrence - must not raise/500, and must not create a
    # second transaction; it should transparently return the winning row.
    second = await transaction_service.create_transaction(
        db_session,
        user_id=user_id,
        data=occurrence,
        idempotency_key=None,
        recurring_transaction_id=recurring_id,
    )
    await db_session.commit()

    assert second.id == first.id

    all_transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    linked = [
        t for t in all_transactions.json()["data"] if t["recurring_transaction_id"] is not None
    ]
    assert len(linked) == 1  # the race never produced a duplicate transaction


async def test_generated_transaction_updates_account_balance(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000000)
    today = date.today()
    await _create_recurring(
        client,
        auth_headers,
        account["id"],
        type="expense",
        amount_minor=50000,
        frequency="daily",
        start_date=today.isoformat(),
    )

    await _generate(client, auth_headers)

    after = await client.get(f"/api/v1/accounts/{account['id']}", headers=auth_headers)
    assert after.json()["data"]["balance_minor"] == 10000000 - 50000


async def test_generated_income_transaction_credits_account_balance(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000000)
    today = date.today()
    await _create_recurring(
        client,
        auth_headers,
        account["id"],
        type="income",
        amount_minor=500000,
        frequency="daily",
        start_date=today.isoformat(),
    )

    await _generate(client, auth_headers)

    after = await client.get(f"/api/v1/accounts/{account['id']}", headers=auth_headers)
    assert after.json()["data"]["balance_minor"] == 10000000 + 500000


async def test_multiple_recurring_transactions_generate_independently(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    start = date.today() - timedelta(days=2)
    netflix = await _create_recurring(
        client,
        auth_headers,
        account["id"],
        name="Netflix",
        frequency="daily",
        start_date=start.isoformat(),
    )
    salary = await _create_recurring(
        client,
        auth_headers,
        account["id"],
        name="Salary",
        type="income",
        frequency="weekly",
        start_date=start.isoformat(),
    )

    generated = await _generate(client, auth_headers)
    netflix_txns = [t for t in generated if t["recurring_transaction_id"] == netflix["id"]]
    salary_txns = [t for t in generated if t["recurring_transaction_id"] == salary["id"]]
    assert len(netflix_txns) == 3  # daily: start, start+1, start+2 (today)
    assert len(salary_txns) == 1  # weekly: just start


# --- the system-wide job (no user-facing endpoint - tested directly) ---------------


async def test_run_for_all_users_generates_across_every_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict, db_session: AsyncSession
) -> None:
    my_account = await _create_account(client, auth_headers)
    their_account = await _create_account(client, other_auth_headers)
    past_start = (date.today() - timedelta(days=1)).isoformat()

    mine = await _create_recurring(
        client, auth_headers, my_account["id"], frequency="daily", start_date=past_start
    )
    theirs = await _create_recurring(
        client, other_auth_headers, their_account["id"], frequency="daily", start_date=past_start
    )

    generated = await recurring_transaction_generator.run_for_all_users(db_session)
    await db_session.commit()

    my_txns = [t for t in generated if str(t.recurring_transaction_id) == mine["id"]]
    their_txns = [t for t in generated if str(t.recurring_transaction_id) == theirs["id"]]
    assert len(my_txns) == 2  # start, today
    assert len(their_txns) == 2

    # Running it again immediately is a no-op for everyone, same as the
    # user-scoped path.
    second_pass = await recurring_transaction_generator.run_for_all_users(db_session)
    await db_session.commit()
    assert second_pass == []
