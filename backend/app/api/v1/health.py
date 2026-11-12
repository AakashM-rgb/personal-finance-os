"""Unauthenticated health check - used by orchestration/monitoring, and by the
frontend to wait for a sleeping backend to wake before restoring a session
(frontend/lib/backend-readiness.ts). It must stay side-effect free: clients
poll, abort, and repeat it freely."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"data": {"status": "ok"}, "error": None, "meta": None}
