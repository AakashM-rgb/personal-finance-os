"""Unauthenticated health check - used by orchestration/monitoring, not by the UI."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"data": {"status": "ok"}, "error": None, "meta": None}
