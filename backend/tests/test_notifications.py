"""Notification generation, listing, read/unread, and preference-gating
tests. Every category is exercised with real, deterministic data - no
fake/random notification content anywhere."""

import asyncio
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Test Account")
    payload.setdefault("type", "bank_account")
    payload.setdefault("balance_minor", 10000000)
    payload.setdefault("currency", "INR")
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


async def _create_transaction(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _list_notifications(client: AsyncClient, headers: dict, **params) -> list[dict]:
    response = await client.get("/api/v1/notifications", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _by_category(notifications: list[dict], category: str) -> list[dict]:
    return [n for n in notifications if n["category"] == category]


# --- authentication ---------------------------------------------------------------------


async def test_list_notifications_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401


async def test_unread_count_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/notifications/unread-count")
    assert response.status_code == 401


async def test_mark_read_requires_authentication(client: AsyncClient) -> None:
    import uuid

    response = await client.put(f"/api/v1/notifications/{uuid.uuid4()}/read")
    assert response.status_code == 401


async def test_mark_all_read_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/notifications/read-all")
    assert response.status_code == 401


# --- budget warning / exceeded -----------------------------------------------------------


async def test_budget_warning_notification_created_at_threshold(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": category_id, "amount_minor": 100000},
    )
    # 75% used - crosses the existing 70% warning threshold, not yet exceeded.
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=75000,
        category_id=category_id,
    )

    notifications = await _list_notifications(client, auth_headers)
    warnings = await _by_category(notifications, "budget_warning")
    exceeded = await _by_category(notifications, "budget_exceeded")
    assert len(warnings) == 1
    assert len(exceeded) == 0
    assert "Food" in warnings[0]["title"]
    assert warnings[0]["reference_type"] == "budget_item"
    assert warnings[0]["action_url"] == "/budgets"


async def test_budget_exceeded_notification_created_over_100_percent(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": category_id, "amount_minor": 100000},
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=150000,
        category_id=category_id,
    )

    notifications = await _list_notifications(client, auth_headers)
    exceeded = await _by_category(notifications, "budget_exceeded")
    warnings = await _by_category(notifications, "budget_warning")
    assert len(exceeded) == 1
    assert len(warnings) == 0  # exceeded, not also warned separately


async def test_budget_warning_not_duplicated_across_repeated_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": category_id, "amount_minor": 100000},
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=80000,
        category_id=category_id,
    )

    first = await _by_category(await _list_notifications(client, auth_headers), "budget_warning")
    second = await _by_category(await _list_notifications(client, auth_headers), "budget_warning")
    third = await _by_category(await _list_notifications(client, auth_headers), "budget_warning")
    assert len(first) == len(second) == len(third) == 1


async def test_budget_below_warning_threshold_creates_no_notification(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": category_id, "amount_minor": 100000},
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=20000,
        category_id=category_id,
    )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "budget_warning") == []
    assert await _by_category(notifications, "budget_exceeded") == []


# --- subscription / credit-card reminders --------------------------------------------------


async def test_subscription_reminder_created_within_window(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today()
    response = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Netflix",
            "account_id": account["id"],
            "amount_minor": 64900,
            "frequency": "monthly",
            "start_date": today.isoformat(),
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    reminders = await _by_category(notifications, "subscription_reminder")
    assert len(reminders) == 1
    assert "Netflix" in reminders[0]["title"]
    assert reminders[0]["action_url"] == "/subscriptions"


async def test_subscription_reminder_not_created_outside_window(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    far_future = date.today() + timedelta(days=60)
    await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Yearly Thing",
            "account_id": account["id"],
            "amount_minor": 999900,
            "frequency": "yearly",
            "start_date": far_future.isoformat(),
        },
    )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "subscription_reminder") == []


async def test_subscription_reminder_not_duplicated_across_repeated_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today()
    await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Netflix",
            "account_id": account["id"],
            "amount_minor": 64900,
            "frequency": "monthly",
            "start_date": today.isoformat(),
        },
    )
    first = await _by_category(
        await _list_notifications(client, auth_headers), "subscription_reminder"
    )
    second = await _by_category(
        await _list_notifications(client, auth_headers), "subscription_reminder"
    )
    assert len(first) == len(second) == 1


async def test_credit_card_reminder_created_for_due_date_today(
    client: AsyncClient, auth_headers: dict
) -> None:
    today = date.today()
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "My Credit Card",
            "type": "credit_card",
            "balance_minor": 0,
            "currency": "INR",
            "credit_card": {
                "credit_limit_minor": 5000000,
                "statement_day": max(today.day - 5, 1),
                "payment_due_day": today.day,
            },
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    reminders = await _by_category(notifications, "credit_card_reminder")
    assert len(reminders) == 1
    assert "My Credit Card" in reminders[0]["title"]


async def test_credit_card_reminder_month_end_clamping(
    client: AsyncClient, auth_headers: dict
) -> None:
    """A payment_due_day of 31 must resolve to a real date even in a
    30-day (or 28/29-day) month - boundary date handling, not a crash."""
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "Card 31",
            "type": "credit_card",
            "balance_minor": 0,
            "currency": "INR",
            "credit_card": {
                "credit_limit_minor": 5000000,
                "statement_day": 1,
                "payment_due_day": 31,
            },
        },
    )
    assert response.status_code == 201, response.text
    # Must not 500 regardless of which month "today" falls in.
    response = await client.get("/api/v1/notifications", headers=auth_headers)
    assert response.status_code == 200


async def test_credit_card_reminder_not_created_for_non_credit_card_account(
    client: AsyncClient, auth_headers: dict
) -> None:
    await _create_account(client, auth_headers, type="bank_account")
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "credit_card_reminder") == []


async def test_multiple_credit_cards_in_window_survive_concurrent_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Regression test for a real bug: the credit-card reminder loop used
    to iterate raw ORM Account objects across multiple create_if_not_exists
    calls. create_if_not_exists rolls back the whole session on a
    duplicate-key race, which expires every loaded ORM object - with two
    credit cards both due for a reminder, a race on the first one's
    dedupe_key used to leave the second account's ORM attributes
    (.name, .credit_card.payment_due_day) expired, and touching them next
    would raise MissingGreenlet instead of a clean response. Firing several
    concurrent requests (each of which triggers generation inline, see
    app.api.v1.notifications) against two qualifying credit cards
    reproduces that exact race - the fix extracts every value the loop
    needs into plain tuples before any create_if_not_exists call runs, so
    a rollback on one account can never affect reading the next one."""
    today = date.today()
    await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "Card One",
            "type": "credit_card",
            "balance_minor": 0,
            "currency": "INR",
            "credit_card": {
                "credit_limit_minor": 5000000,
                "statement_day": max(today.day - 5, 1),
                "payment_due_day": today.day,
            },
        },
    )
    await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "Card Two",
            "type": "credit_card",
            "balance_minor": 0,
            "currency": "INR",
            "credit_card": {
                "credit_limit_minor": 5000000,
                "statement_day": max(today.day - 5, 1),
                "payment_due_day": today.day,
            },
        },
    )

    # Several concurrent requests each independently trigger
    # generate_due_for_user inline - with two qualifying credit cards in
    # every one of them, this reliably exercises the duplicate-key race on
    # at least one of the two dedupe_keys across the overlapping calls.
    responses = await asyncio.gather(
        *[client.get("/api/v1/notifications", headers=auth_headers) for _ in range(8)]
    )
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]

    notifications = await _list_notifications(client, auth_headers)
    reminders = await _by_category(notifications, "credit_card_reminder")
    titles = {n["title"] for n in reminders}
    assert titles == {"Card One payment due soon", "Card Two payment due soon"}
    assert len(reminders) == 2  # exactly one notification per card, never duplicated

    # Repeated generation afterwards remains idempotent.
    again = await _by_category(
        await _list_notifications(client, auth_headers), "credit_card_reminder"
    )
    assert len(again) == 2


# --- savings goal milestones --------------------------------------------------------------


async def test_goal_milestone_notification_at_50_percent(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Emergency Fund",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    milestones = await _by_category(notifications, "goal_milestone")
    # 500000/1000000 = 50% crosses both the 25% and 50% milestones.
    assert {n["title"] for n in milestones} == {
        "Emergency Fund is 25% funded",
        "Emergency Fund is 50% funded",
    }


async def test_goal_milestone_notification_at_100_percent(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Full Goal",
            "target_amount_minor": 500000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    milestones = await _by_category(notifications, "goal_milestone")
    titles = {n["title"] for n in milestones}
    assert "Full Goal goal reached!" in titles
    assert len(milestones) == 4  # 25, 50, 75, 100 all crossed at once


async def test_goal_milestone_not_duplicated_across_repeated_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Repeat Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 250000,
            "target_date": "2027-06-01",
        },
    )
    first = await _by_category(await _list_notifications(client, auth_headers), "goal_milestone")
    second = await _by_category(await _list_notifications(client, auth_headers), "goal_milestone")
    assert len(first) == len(second) == 1


async def test_goal_below_first_milestone_creates_no_notification(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Tiny Progress",
            "target_amount_minor": 1000000,
            "current_amount_minor": 10000,
            "target_date": "2027-06-01",
        },
    )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "goal_milestone") == []


async def test_goal_milestone_message_states_amount_for_that_milestone_on_full_backfill(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Jumping straight from 0% to 100% backfills all four milestones in one
    # generation pass - each message must quote ITS OWN threshold amount
    # (target * milestone%), not the goal's final current_amount_minor.
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Amount Check",
            "target_amount_minor": 1000000,
            "current_amount_minor": 1000000,
            "target_date": "2027-06-01",
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    milestones = await _by_category(notifications, "goal_milestone")
    by_title = {n["title"]: n["message"] for n in milestones}
    assert len(by_title) == 4

    assert by_title["Amount Check is 25% funded"] == (
        "You've saved 2500.00 INR of your 10000.00 INR target for Amount Check."
    )
    assert by_title["Amount Check is 50% funded"] == (
        "You've saved 5000.00 INR of your 10000.00 INR target for Amount Check."
    )
    assert by_title["Amount Check is 75% funded"] == (
        "You've saved 7500.00 INR of your 10000.00 INR target for Amount Check."
    )
    assert by_title["Amount Check goal reached!"] == (
        "You've saved 10000.00 INR of your 10000.00 INR target for Amount Check."
    )


async def test_goal_milestone_message_states_threshold_amount_not_current_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Landing exactly on 50% still backfills the 25% milestone. Before the
    # fix, the 25% message wrongly quoted the goal's current amount (50% of
    # target) instead of the 25% threshold amount.
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Threshold Check",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    milestones = await _by_category(notifications, "goal_milestone")
    by_title = {n["title"]: n["message"] for n in milestones}
    assert set(by_title) == {"Threshold Check is 25% funded", "Threshold Check is 50% funded"}

    assert by_title["Threshold Check is 25% funded"] == (
        "You've saved 2500.00 INR of your 10000.00 INR target for Threshold Check."
    )
    assert by_title["Threshold Check is 50% funded"] == (
        "You've saved 5000.00 INR of your 10000.00 INR target for Threshold Check."
    )


async def test_goal_milestones_crossed_one_at_a_time_each_get_correct_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Step Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 250000,
            "target_date": "2027-06-01",
        },
    )
    goal_id = create_response.json()["data"]["id"]

    notifications = await _list_notifications(client, auth_headers)
    first_pass = await _by_category(notifications, "goal_milestone")
    assert {n["title"]: n["message"] for n in first_pass} == {
        "Step Goal is 25% funded": (
            "You've saved 2500.00 INR of your 10000.00 INR target for Step Goal."
        )
    }

    update_response = await client.put(
        f"/api/v1/goals/{goal_id}",
        headers=auth_headers,
        json={"current_amount_minor": 500000},
    )
    assert update_response.status_code == 200, update_response.text

    notifications = await _list_notifications(client, auth_headers)
    second_pass = await _by_category(notifications, "goal_milestone")
    by_title = {n["title"]: n["message"] for n in second_pass}
    assert set(by_title) == {"Step Goal is 25% funded", "Step Goal is 50% funded"}
    # The 25% notification, generated back when current was only 25%, is
    # untouched by the later update to 50%.
    assert by_title["Step Goal is 25% funded"] == (
        "You've saved 2500.00 INR of your 10000.00 INR target for Step Goal."
    )
    assert by_title["Step Goal is 50% funded"] == (
        "You've saved 5000.00 INR of your 10000.00 INR target for Step Goal."
    )


async def test_goal_milestone_repeated_generation_does_not_duplicate_or_change_message(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Stable Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )

    first = await _by_category(await _list_notifications(client, auth_headers), "goal_milestone")
    second = await _by_category(await _list_notifications(client, auth_headers), "goal_milestone")
    assert len(first) == len(second) == 2
    assert {n["title"]: n["message"] for n in first} == {n["title"]: n["message"] for n in second}


async def test_goal_milestone_amount_uses_integer_minor_units_no_float_artifacts(
    client: AsyncClient, auth_headers: dict
) -> None:
    # target not evenly divisible by 4 (or 100): the milestone amount must
    # still be a clean integer-minor-unit money string, never a raw float
    # repr like "3333.3333333333335".
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Odd Target",
            "target_amount_minor": 999999,
            "current_amount_minor": 999999,
            "target_date": "2027-06-01",
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    milestones = await _by_category(notifications, "goal_milestone")
    by_title = {n["title"]: n["message"] for n in milestones}

    # 999999 * 25 // 100 = 249999 minor units = 2499.99 INR
    assert by_title["Odd Target is 25% funded"] == (
        "You've saved 2499.99 INR of your 9999.99 INR target for Odd Target."
    )
    assert by_title["Odd Target goal reached!"] == (
        "You've saved 9999.99 INR of your 9999.99 INR target for Odd Target."
    )


# --- recurring expense reminders ----------------------------------------------------------


async def test_recurring_reminder_created_within_window(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Bills")
    today = date.today()
    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Rent",
            "account_id": account["id"],
            "category_id": category_id,
            "type": "expense",
            "amount_minor": 500000,
            "frequency": "monthly",
            "start_date": today.isoformat(),
        },
    )
    assert response.status_code == 201, response.text

    notifications = await _list_notifications(client, auth_headers)
    reminders = await _by_category(notifications, "recurring_reminder")
    assert len(reminders) == 1
    assert "Rent" in reminders[0]["title"]


async def test_recurring_reminder_not_created_for_income(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Bills")
    today = date.today()
    await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Salary",
            "account_id": account["id"],
            "category_id": category_id,
            "type": "income",
            "amount_minor": 5000000,
            "frequency": "monthly",
            "start_date": today.isoformat(),
        },
    )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "recurring_reminder") == []


async def test_recurring_reminder_not_duplicated_across_repeated_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Bills")
    today = date.today()
    await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Rent",
            "account_id": account["id"],
            "category_id": category_id,
            "type": "expense",
            "amount_minor": 500000,
            "frequency": "monthly",
            "start_date": today.isoformat(),
        },
    )
    first = await _by_category(
        await _list_notifications(client, auth_headers), "recurring_reminder"
    )
    second = await _by_category(
        await _list_notifications(client, auth_headers), "recurring_reminder"
    )
    assert len(first) == len(second) == 1


async def test_recurring_reminder_excludes_a_subscriptions_own_schedule(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Regression test: a subscription is a 1:1 extension of a recurring
    transaction (CLAUDE.md §4) - its own backing schedule must not ALSO
    generate a recurring_reminder, or a single subscription renewal would
    redundantly notify the user twice (once per category) for the same
    real-world event."""
    account = await _create_account(client, auth_headers)
    today = date.today()
    await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Netflix",
            "account_id": account["id"],
            "amount_minor": 64900,
            "frequency": "monthly",
            "start_date": today.isoformat(),
        },
    )
    notifications = await _list_notifications(client, auth_headers)
    assert len(await _by_category(notifications, "subscription_reminder")) == 1
    assert await _by_category(notifications, "recurring_reminder") == []


# --- unusual spending ----------------------------------------------------------------------


async def test_unusual_spending_flagged_above_threshold(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    for _ in range(5):
        await _create_transaction(
            client,
            auth_headers,
            account_id=account["id"],
            type="expense",
            amount_minor=10000,
            category_id=category_id,
        )
    # Average of the 5 prior transactions is 10000; 3x that is 30000 - this
    # one is well above it.
    unusual_txn = await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=50000,
        category_id=category_id,
    )

    notifications = await _list_notifications(client, auth_headers)
    flagged = await _by_category(notifications, "unusual_spending")
    assert len(flagged) == 1
    assert flagged[0]["reference_id"] == unusual_txn["id"]


async def test_unusual_spending_not_flagged_with_insufficient_history(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    # Only 2 prior transactions - below the minimum sample size, so even a
    # huge outlier must not be flagged (no guess without enough evidence).
    for _ in range(2):
        await _create_transaction(
            client,
            auth_headers,
            account_id=account["id"],
            type="expense",
            amount_minor=10000,
            category_id=category_id,
        )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=500000,
        category_id=category_id,
    )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "unusual_spending") == []


async def test_unusual_spending_not_flagged_within_normal_range(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    for _ in range(6):
        await _create_transaction(
            client,
            auth_headers,
            account_id=account["id"],
            type="expense",
            amount_minor=10000,
            category_id=category_id,
        )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "unusual_spending") == []


async def test_unusual_spending_not_duplicated_across_repeated_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    for _ in range(5):
        await _create_transaction(
            client,
            auth_headers,
            account_id=account["id"],
            type="expense",
            amount_minor=10000,
            category_id=category_id,
        )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=50000,
        category_id=category_id,
    )
    first = await _by_category(await _list_notifications(client, auth_headers), "unusual_spending")
    second = await _by_category(await _list_notifications(client, auth_headers), "unusual_spending")
    assert len(first) == len(second) == 1


# --- preference gating -----------------------------------------------------------------------


async def test_disabled_category_generates_no_notification(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"budget_warnings": False}},
    )
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": category_id, "amount_minor": 100000},
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=150000,
        category_id=category_id,
    )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "budget_exceeded") == []
    assert await _by_category(notifications, "budget_warning") == []


async def test_re_enabling_category_resumes_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"goal_milestones": False}},
    )
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Gated Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    assert (
        await _by_category(await _list_notifications(client, auth_headers), "goal_milestone") == []
    )

    await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"goal_milestones": True}},
    )
    resumed = await _by_category(await _list_notifications(client, auth_headers), "goal_milestone")
    assert len(resumed) > 0


async def test_disabling_one_category_leaves_others_generating(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"budget_warnings": False}},
    )
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": category_id, "amount_minor": 100000},
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=150000,
        category_id=category_id,
    )
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Still Active",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    notifications = await _list_notifications(client, auth_headers)
    assert await _by_category(notifications, "budget_exceeded") == []
    assert len(await _by_category(notifications, "goal_milestone")) > 0


# --- read / unread behavior --------------------------------------------------------------


async def test_new_notification_starts_unread(client: AsyncClient, auth_headers: dict) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Unread Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    notifications = await _list_notifications(client, auth_headers)
    assert all(n["is_read"] is False for n in notifications)

    count_response = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert count_response.status_code == 200
    assert count_response.json()["data"]["unread_count"] == len(notifications)


async def test_mark_one_notification_read(client: AsyncClient, auth_headers: dict) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Mark Read Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    notifications = await _list_notifications(client, auth_headers)
    target = notifications[0]

    response = await client.put(f"/api/v1/notifications/{target['id']}/read", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["is_read"] is True

    refreshed = await _list_notifications(client, auth_headers)
    updated = next(n for n in refreshed if n["id"] == target["id"])
    assert updated["is_read"] is True
    # The other milestone notification(s) from the same goal remain unread.
    assert any(n["is_read"] is False for n in refreshed if n["id"] != target["id"])


async def test_mark_read_unknown_id_returns_404(client: AsyncClient, auth_headers: dict) -> None:
    import uuid

    response = await client.put(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=auth_headers)
    assert response.status_code == 404


async def test_mark_all_read(client: AsyncClient, auth_headers: dict) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Mark All Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    before = await _list_notifications(client, auth_headers)
    assert len(before) > 1  # 25% and 50% milestones both fired

    response = await client.post("/api/v1/notifications/read-all", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["updated_count"] == len(before)

    after = await _list_notifications(client, auth_headers)
    assert all(n["is_read"] is True for n in after)

    count_response = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert count_response.json()["data"]["unread_count"] == 0


async def test_unread_only_filter(client: AsyncClient, auth_headers: dict) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Filter Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    all_notifications = await _list_notifications(client, auth_headers)
    await client.put(
        f"/api/v1/notifications/{all_notifications[0]['id']}/read", headers=auth_headers
    )

    unread_only = await _list_notifications(client, auth_headers, unread_only=True)
    assert all_notifications[0]["id"] not in {n["id"] for n in unread_only}
    assert len(unread_only) == len(all_notifications) - 1


# --- user isolation / IDOR ------------------------------------------------------------------


async def test_notifications_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "A's Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    own = await _list_notifications(client, auth_headers)
    other = await _list_notifications(client, other_auth_headers)
    assert len(own) > 0
    assert other == []


async def test_cannot_mark_another_users_notification_read(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Private Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    mine = await _list_notifications(client, auth_headers)
    target_id = mine[0]["id"]

    response = await client.put(
        f"/api/v1/notifications/{target_id}/read", headers=other_auth_headers
    )
    assert response.status_code == 404

    # Confirm it is genuinely untouched, not silently marked read anyway.
    still_mine = await _list_notifications(client, auth_headers)
    unchanged = next(n for n in still_mine if n["id"] == target_id)
    assert unchanged["is_read"] is False


async def test_mark_all_read_never_touches_another_users_notifications(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "A's Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    await client.post(
        "/api/v1/goals",
        headers=other_auth_headers,
        json={
            "name": "B's Goal",
            "target_amount_minor": 1000000,
            "current_amount_minor": 500000,
            "target_date": "2027-06-01",
        },
    )
    await client.post("/api/v1/notifications/read-all", headers=auth_headers)

    others_notifications = await _list_notifications(client, other_auth_headers)
    assert all(n["is_read"] is False for n in others_notifications)


# --- generation is idempotent under concurrency ---------------------------------------------


async def test_concurrent_generation_never_creates_duplicates(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Fires several concurrent `GET /notifications` calls (each of which
    triggers generation inline) against the same fresh budget-exceeded
    condition - the database's own unique constraint
    (uq_notifications_user_dedupe_key), not request ordering, must be what
    prevents a duplicate, exactly like the recurring-transaction
    generation race this mirrors."""
    account = await _create_account(client, auth_headers)
    category_id = await _get_category_id(client, auth_headers, "Food")
    await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": category_id, "amount_minor": 100000},
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=150000,
        category_id=category_id,
    )

    responses = await asyncio.gather(
        *[client.get("/api/v1/notifications", headers=auth_headers) for _ in range(8)]
    )
    assert all(r.status_code == 200 for r in responses)

    final = await _list_notifications(client, auth_headers)
    exceeded = await _by_category(final, "budget_exceeded")
    assert len(exceeded) == 1


# --- direct service-layer test for the exact race window ------------------------------------


async def test_service_recovers_from_a_true_dedupe_key_race(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    """Deterministically forces the exact race two concurrent generation
    calls could hit: both attempt to insert a Notification with the same
    (user_id, dedupe_key) because both ran their "does this already exist"
    read before either had committed. create_if_not_exists must recover by
    returning None, never a raw IntegrityError/500."""
    import uuid as uuid_module

    from app.models.notification import NotificationCategory
    from app.repositories.notification_repository import NotificationRepository

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = uuid_module.UUID(me.json()["data"]["id"])
    repo = NotificationRepository(db_session)

    first = await repo.create_if_not_exists(
        user_id=user_id,
        category=NotificationCategory.UNUSUAL_SPENDING,
        title="Race Test",
        message="Race test message.",
        dedupe_key="race-test-key",
    )
    await db_session.commit()
    assert first is not None

    second = await repo.create_if_not_exists(
        user_id=user_id,
        category=NotificationCategory.UNUSUAL_SPENDING,
        title="Race Test",
        message="Race test message.",
        dedupe_key="race-test-key",
    )
    await db_session.commit()
    assert second is None  # recovered as a no-op, never raised
