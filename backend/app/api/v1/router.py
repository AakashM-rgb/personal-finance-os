from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    ai,
    analytics,
    auth,
    budgets,
    calendar,
    categories,
    dashboard,
    goals,
    health,
    receipts,
    recurring_transactions,
    reports,
    search,
    subscriptions,
    transactions,
    user_settings,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(dashboard.router)
api_router.include_router(budgets.router)
api_router.include_router(goals.router)
api_router.include_router(recurring_transactions.router)
api_router.include_router(subscriptions.router)
api_router.include_router(analytics.router)
api_router.include_router(calendar.router)
api_router.include_router(reports.router)
api_router.include_router(receipts.router)
api_router.include_router(ai.router)
api_router.include_router(search.router)
api_router.include_router(user_settings.router)
