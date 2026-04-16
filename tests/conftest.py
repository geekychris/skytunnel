"""Shared test fixtures."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tunnelctl.config import AppConfig, EndpointConfig, GlobalConfig, ProxyConfig, TelegramConfig, TunnelConfig
from tunnelctl.state import StateStore


@pytest.fixture
def sample_config() -> AppConfig:
    return AppConfig.model_validate({
        "global": {
            "reconnect_interval": 5,
            "health_check_interval": 10,
            "health_check_timeout": 5,
            "log_level": "DEBUG",
            "state_db": ":memory:",
            "api_port": 8080,
            "api_host": "127.0.0.1",
        },
        "telegram": {"enabled": False},
        "endpoints": [
            {
                "name": "test-server",
                "host": "localhost",
                "port": 2222,
                "user": "test",
                "key_file": "~/.ssh/test_key",
                "proxy": {
                    "type": "nginx",
                    "http_domain": "*.test.local",
                    "ssl": False,
                },
            },
            {
                "name": "test-cloud",
                "host": "10.0.0.1",
                "port": 22,
                "user": "tunnel",
                "key_file": "~/.ssh/test_key",
            },
        ],
        "tunnels": [
            {
                "name": "web",
                "internal_host": "192.168.1.10",
                "internal_port": 80,
                "remote_port": 8080,
                "protocol": "http",
                "endpoints": ["test-server", "test-cloud"],
                "subdomain": "web",
            },
            {
                "name": "ssh",
                "internal_host": "192.168.1.10",
                "internal_port": 22,
                "remote_port": 2222,
                "protocol": "tcp",
                "endpoints": ["test-server"],
            },
        ],
    })


@pytest_asyncio.fixture
async def state_store() -> StateStore:
    store = StateStore()
    await store.init(":memory:")
    yield store
    await store.close()
