"""Tests for the FastAPI API routes."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tunnelctl.api.app import create_app
from tunnelctl.state import StateStore


@pytest_asyncio.fixture
async def client(sample_config, state_store, tmp_path):
    config_path = tmp_path / "config.yaml"
    # Write a minimal config for reload tests
    import yaml

    data = {
        "global": sample_config.global_.model_dump(),
        "telegram": sample_config.telegram.model_dump(),
        "endpoints": [ep.model_dump() for ep in sample_config.endpoints],
        "tunnels": [t.model_dump() for t in sample_config.tunnels],
    }
    config_path.write_text(yaml.dump(data))

    app = create_app(sample_config, config_path, state_store)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_tunnels(client):
    resp = await client.get("/api/tunnels")
    assert resp.status_code == 200
    tunnels = resp.json()
    assert len(tunnels) == 2
    assert tunnels[0]["name"] == "web"


@pytest.mark.asyncio
async def test_list_endpoints(client):
    resp = await client.get("/api/endpoints")
    assert resp.status_code == 200
    endpoints = resp.json()
    assert len(endpoints) == 2


@pytest.mark.asyncio
async def test_get_status_empty(client):
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_add_and_remove_tunnel(client):
    # Add a tunnel
    resp = await client.post("/api/tunnels", json={
        "name": "new-tunnel",
        "internal_host": "192.168.1.50",
        "internal_port": 443,
        "remote_port": 9443,
        "protocol": "tcp",
    })
    assert resp.status_code == 200
    assert "added" in resp.json()["message"].lower()

    # Verify it's in the list
    resp = await client.get("/api/tunnels")
    names = [t["name"] for t in resp.json()]
    assert "new-tunnel" in names

    # Remove it
    resp = await client.delete("/api/tunnels/new-tunnel")
    assert resp.status_code == 200

    # Verify it's gone
    resp = await client.get("/api/tunnels")
    names = [t["name"] for t in resp.json()]
    assert "new-tunnel" not in names


@pytest.mark.asyncio
async def test_add_duplicate_tunnel(client):
    resp = await client.post("/api/tunnels", json={
        "name": "web",  # already exists
        "internal_host": "192.168.1.50",
        "internal_port": 80,
        "remote_port": 9080,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_remove_nonexistent_tunnel(client):
    resp = await client.delete("/api/tunnels/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_logs_empty(client):
    resp = await client.get("/api/logs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_config_reload(client):
    resp = await client.post("/api/config/reload")
    assert resp.status_code == 200
    assert "reloaded" in resp.json()["message"].lower()
