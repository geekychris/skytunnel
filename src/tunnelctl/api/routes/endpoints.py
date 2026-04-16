"""Endpoint API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["endpoints"])


@router.get("/endpoints")
async def list_endpoints(request: Request):
    app_state = request.app.state.tunnelctl
    return [ep.model_dump() for ep in app_state.config.endpoints]
