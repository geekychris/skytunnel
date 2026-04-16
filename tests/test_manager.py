"""Tests for TunnelManager (with mocked SSH)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tunnelctl.agent.manager import TunnelManager


@pytest.mark.asyncio
async def test_manager_builds_correct_tunnel_pairs(sample_config, state_store):
    """Manager should create a SingleTunnel for each (tunnel, endpoint) pair."""
    manager = TunnelManager(sample_config, state_store)

    # Mock SingleTunnel.start to avoid actual SSH connections
    with patch("tunnelctl.agent.manager.SingleTunnel") as MockTunnel:
        mock_instance = AsyncMock()
        MockTunnel.return_value = mock_instance

        await manager.start_all()

        # "web" targets [test-server, test-cloud] = 2 tunnels
        # "ssh" targets [test-server] = 1 tunnel
        # Total: 3
        assert len(manager.get_tunnel_keys()) == 3
        assert "web@test-server" in manager.get_tunnel_keys()
        assert "web@test-cloud" in manager.get_tunnel_keys()
        assert "ssh@test-server" in manager.get_tunnel_keys()


@pytest.mark.asyncio
async def test_manager_remove_tunnel(sample_config, state_store):
    manager = TunnelManager(sample_config, state_store)

    with patch("tunnelctl.agent.manager.SingleTunnel") as MockTunnel:
        mock_instance = AsyncMock()
        MockTunnel.return_value = mock_instance

        await manager.start_all()
        assert len(manager.get_tunnel_keys()) == 3

        removed = await manager.remove_tunnel("web")
        assert len(removed) == 2
        assert len(manager.get_tunnel_keys()) == 1
        assert "ssh@test-server" in manager.get_tunnel_keys()


@pytest.mark.asyncio
async def test_manager_empty_endpoints_means_all(state_store):
    """A tunnel with empty endpoints list should target all endpoints."""
    from tunnelctl.config import AppConfig

    cfg = AppConfig.model_validate({
        "endpoints": [
            {"name": "ep1", "host": "h1"},
            {"name": "ep2", "host": "h2"},
        ],
        "tunnels": [
            {
                "name": "everywhere",
                "internal_host": "192.168.1.1",
                "internal_port": 22,
                "remote_port": 3333,
                "endpoints": [],  # all endpoints
            },
        ],
    })
    manager = TunnelManager(cfg, state_store)

    with patch("tunnelctl.agent.manager.SingleTunnel") as MockTunnel:
        MockTunnel.return_value = AsyncMock()
        await manager.start_all()

        assert len(manager.get_tunnel_keys()) == 2
        assert "everywhere@ep1" in manager.get_tunnel_keys()
        assert "everywhere@ep2" in manager.get_tunnel_keys()
