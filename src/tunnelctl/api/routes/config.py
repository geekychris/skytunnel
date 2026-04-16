"""Config management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from tunnelctl.config import load_config

router = APIRouter(tags=["config"])


@router.post("/config/reload")
async def reload_config(request: Request):
    app_state = request.app.state.tunnelctl
    try:
        new_config = load_config(app_state.config_path)
    except Exception as e:
        raise HTTPException(400, f"Config error: {e}")

    if app_state.manager:
        await app_state.manager.reload(new_config)

    app_state.config = new_config
    return {"message": "Configuration reloaded", "tunnels": len(new_config.tunnels)}
