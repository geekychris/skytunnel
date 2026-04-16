"""Tests for NGINX config generation."""

from __future__ import annotations

import pytest

from tunnelctl.config import EndpointConfig, ProxyConfig, TunnelConfig
from tunnelctl.endpoint.nginx import NginxConfigGenerator


@pytest.fixture
def endpoint():
    return EndpointConfig(
        name="test-server",
        host="example.com",
        proxy=ProxyConfig(
            type="nginx",
            http_domain="*.test.example.com",
            ssl=True,
            config_path="/tmp/test-nginx.conf",
        ),
    )


@pytest.fixture
def tunnels():
    return [
        TunnelConfig(
            name="web",
            internal_host="192.168.1.10",
            internal_port=80,
            remote_port=8080,
            protocol="http",
            endpoints=["test-server"],
            subdomain="web",
        ),
        TunnelConfig(
            name="api",
            internal_host="192.168.1.10",
            internal_port=3000,
            remote_port=8081,
            protocol="http",
            endpoints=["test-server"],
            subdomain="api",
        ),
        TunnelConfig(
            name="ssh",
            internal_host="192.168.1.10",
            internal_port=22,
            remote_port=2222,
            protocol="tcp",
            endpoints=["test-server"],
        ),
    ]


def test_http_config_generation(endpoint, tunnels):
    gen = NginxConfigGenerator(endpoint)
    http_config, stream_config = gen.generate(tunnels)

    assert "web.test.example.com" in http_config
    assert "api.test.example.com" in http_config
    assert "proxy_pass http://127.0.0.1:8080" in http_config
    assert "proxy_pass http://127.0.0.1:8081" in http_config


def test_stream_config_generation(endpoint, tunnels):
    gen = NginxConfigGenerator(endpoint)
    http_config, stream_config = gen.generate(tunnels)

    assert "proxy_pass 127.0.0.1:2222" in stream_config


def test_filters_by_endpoint(endpoint, tunnels):
    # Add a tunnel targeting a different endpoint
    tunnels.append(
        TunnelConfig(
            name="other",
            internal_host="192.168.1.99",
            internal_port=80,
            remote_port=9999,
            protocol="http",
            endpoints=["other-server"],  # not our endpoint
            subdomain="other",
        )
    )
    gen = NginxConfigGenerator(endpoint)
    http_config, _ = gen.generate(tunnels)

    assert "other.test.example.com" not in http_config


def test_domain_stripping(endpoint):
    gen = NginxConfigGenerator(endpoint)
    assert gen.domain == "test.example.com"
