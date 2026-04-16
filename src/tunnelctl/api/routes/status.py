"""Status API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["status"])


@router.get("/status")
async def get_all_statuses(request: Request):
    app_state = request.app.state.tunnelctl
    statuses = await app_state.state.get_all_statuses()
    return [
        {
            "endpoint": s.endpoint,
            "tunnel": s.tunnel,
            "status": s.status,
            "error": s.error,
            "last_connected": s.last_connected,
            "updated_at": s.updated_at,
        }
        for s in statuses
    ]


@router.get("/status/{endpoint}")
async def get_endpoint_statuses(endpoint: str, request: Request):
    app_state = request.app.state.tunnelctl
    statuses = await app_state.state.get_endpoint_statuses(endpoint)
    return [
        {
            "endpoint": s.endpoint,
            "tunnel": s.tunnel,
            "status": s.status,
            "error": s.error,
            "last_connected": s.last_connected,
            "updated_at": s.updated_at,
        }
        for s in statuses
    ]


@router.get("/logs")
async def get_logs(request: Request, limit: int = 100, tunnel: str | None = None):
    app_state = request.app.state.tunnelctl
    logs = await app_state.state.get_logs(limit=limit, tunnel=tunnel)
    return [
        {
            "timestamp": log.timestamp,
            "level": log.level,
            "message": log.message,
            "tunnel": log.tunnel,
        }
        for log in logs
    ]
