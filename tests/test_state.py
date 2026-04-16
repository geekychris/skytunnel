"""Tests for the state store."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_tunnel_status_lifecycle(state_store):
    await state_store.set_tunnel_status("ep1", "tunnel1", "connecting")
    statuses = await state_store.get_all_statuses()
    assert len(statuses) == 1
    assert statuses[0].status == "connecting"

    await state_store.set_tunnel_status("ep1", "tunnel1", "connected")
    statuses = await state_store.get_all_statuses()
    assert statuses[0].status == "connected"
    assert statuses[0].last_connected is not None


@pytest.mark.asyncio
async def test_multiple_tunnels(state_store):
    await state_store.set_tunnel_status("ep1", "t1", "connected")
    await state_store.set_tunnel_status("ep1", "t2", "disconnected")
    await state_store.set_tunnel_status("ep2", "t1", "connecting")

    all_statuses = await state_store.get_all_statuses()
    assert len(all_statuses) == 3

    ep1_statuses = await state_store.get_endpoint_statuses("ep1")
    assert len(ep1_statuses) == 2


@pytest.mark.asyncio
async def test_logs(state_store):
    await state_store.append_log("INFO", "test message")
    await state_store.append_log("ERROR", "error message", tunnel="t1")

    logs = await state_store.get_logs()
    assert len(logs) == 2

    filtered = await state_store.get_logs(tunnel="t1")
    assert len(filtered) == 1
    assert filtered[0].level == "ERROR"


@pytest.mark.asyncio
async def test_log_limit(state_store):
    for i in range(20):
        await state_store.append_log("INFO", f"message {i}")

    logs = await state_store.get_logs(limit=5)
    assert len(logs) == 5
