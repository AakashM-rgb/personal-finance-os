from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    auth,
    budgets,
    categories,
    dashboard,
    goals,
    health,
    recurring_transactions,
    subscriptions,
    transactions,
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
