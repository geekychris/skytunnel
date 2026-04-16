"""Tunnel CRUD API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from tunnelctl.config import TunnelConfig, load_config

router = APIRouter(tags=["tunnels"])


class TunnelCreate(BaseModel):
    name: str
    internal_host: str
    internal_port: int
    remote_port: int
    protocol: str = "tcp"
    endpoints: list[str] = []
    subdomain: str | None = None


@router.get("/tunnels")
async def list_tunnels(request: Request):
    app_state = request.app.state.tunnelctl
    return [t.model_dump() for t in app_state.config.tunnels]


@router.post("/tunnels")
async def add_tunnel(tunnel: TunnelCreate, request: Request):
    app_state = request.app.state.tunnelctl

    # Check for duplicate name
    if any(t.name == tunnel.name for t in app_state.config.tunnels):
        raise HTTPException(400, f"Tunnel '{tunnel.name}' already exists")

    tc = TunnelConfig(**tunnel.model_dump())
    app_state.config.tunnels.append(tc)

    # Save to YAML
    _save_config(app_state)

    # Start the tunnel if manager is running
    if app_state.manager:
        started = await app_state.manager.add_tunnel(tunnel.name)
        return {"message": f"Tunnel added, started {len(started)} connection(s)", "started": started}

    return {"message": "Tunnel added to config"}


@router.delete("/tunnels/{name}")
async def remove_tunnel(name: str, request: Request):
    app_state = request.app.state.tunnelctl

    tunnel = next((t for t in app_state.config.tunnels if t.name == name), None)
    if not tunnel:
        raise HTTPException(404, f"Tunnel '{name}' not found")

    app_state.config.tunnels.remove(tunnel)
    _save_config(app_state)

    if app_state.manager:
        removed = await app_state.manager.remove_tunnel(name)
        return {"message": f"Tunnel removed, stopped {len(removed)} connection(s)", "removed": removed}

    return {"message": "Tunnel removed from config"}


@router.put("/tunnels/{name}")
async def update_tunnel(name: str, tunnel: TunnelCreate, request: Request):
    app_state = request.app.state.tunnelctl

    idx = next((i for i, t in enumerate(app_state.config.tunnels) if t.name == name), None)
    if idx is None:
        raise HTTPException(404, f"Tunnel '{name}' not found")

    # Stop old, update config, start new
    if app_state.manager:
        await app_state.manager.remove_tunnel(name)

    tc = TunnelConfig(**tunnel.model_dump())
    app_state.config.tunnels[idx] = tc
    _save_config(app_state)

    if app_state.manager:
        started = await app_state.manager.add_tunnel(tunnel.name)
        return {"message": f"Tunnel updated, restarted {len(started)} connection(s)"}

    return {"message": "Tunnel updated in config"}


def _save_config(app_state) -> None:
    """Write the current config back to the YAML file."""
    import yaml

    data = {
        "global": app_state.config.global_.model_dump(),
        "telegram": app_state.config.telegram.model_dump(),
        "endpoints": [ep.model_dump() for ep in app_state.config.endpoints],
        "tunnels": [t.model_dump() for t in app_state.config.tunnels],
    }
    with open(app_state.config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
