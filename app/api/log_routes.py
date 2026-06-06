"""
app/api/log_routes.py

Live log streaming + history endpoints.

  GET /api/v1/logs/stream   — SSE, streams dev + agent log entries in real time
  GET /api/v1/logs/dev      — JSON history (last N dev entries)
  GET /api/v1/logs/agent    — JSON history (last N agent entries)

All endpoints require a valid session (cookie or Bearer token).
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.auth.jwt import TokenData
from app.infra.logger import rfp_logger
from app.api.openapi_responses import responses, UNAUTHORIZED

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get(
    "/stream",
    summary="Stream dev + agent logs (SSE)",
    responses=responses(UNAUTHORIZED),
)
async def stream_logs(
    request: Request,
    run_id: Optional[str] = None,
    user: TokenData = Depends(get_current_user),
):
    """
    SSE — streams dev + agent log entries live.
    Replays recent history on connect so the page loads populated.
    Scoped to the caller's org_id automatically.
    """
    org_id = user.org_id
    queue  = rfp_logger.subscribe()

    async def generate():
        # Replay history so the panel isn't blank on load
        for e in rfp_logger.get_dev_history(run_id=run_id, org_id=org_id, limit=200):
            yield f"data: {json.dumps(e)}\n\n"
        for e in rfp_logger.get_agent_history(run_id=run_id, org_id=org_id, limit=100):
            yield f"data: {json.dumps(e)}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    # Scope to caller's org
                    if entry.get("org_id") and entry["org_id"] != org_id:
                        continue
                    # Scope to run_id if requested
                    if run_id and entry.get("run_id") and entry["run_id"] != run_id:
                        continue
                    yield f"data: {json.dumps(entry)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            rfp_logger.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/dev",
    summary="Get recent developer log entries",
    responses=responses(UNAUTHORIZED),
)
async def get_dev_log(
    run_id: Optional[str] = None,
    limit: int = 500,
    user: TokenData = Depends(get_current_user),
):
    """Return the most recent developer log entries (optionally filtered by
    run_id), scoped to the caller's org."""
    return {"entries": rfp_logger.get_dev_history(
        run_id=run_id, org_id=user.org_id, limit=limit
    )}


@router.get(
    "/agent",
    summary="Get recent agent log entries",
    responses=responses(UNAUTHORIZED),
)
async def get_agent_log(
    run_id: Optional[str] = None,
    limit: int = 200,
    user: TokenData = Depends(get_current_user),
):
    """Return the most recent agent log entries (optionally filtered by run_id),
    scoped to the caller's org."""
    return {"entries": rfp_logger.get_agent_history(
        run_id=run_id, org_id=user.org_id, limit=limit
    )}
