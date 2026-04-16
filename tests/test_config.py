"""Tests for configuration loading."""

from __future__ import annotations

import os
import tempfile

import pytest

from tunnelctl.config import AppConfig, load_config


def test_load_config_basic(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
global:
  reconnect_interval: 15
  api_port: 9090

endpoints:
  - name: my-server
    host: example.com
    port: 22
    user: tunnel
    key_file: ~/.ssh/id_ed25519

tunnels:
  - name: web
    internal_host: 192.168.1.1
    internal_port: 80
    remote_port: 8080
    protocol: http
    subdomain: web
""")
    cfg = load_config(config_file)
    assert cfg.global_.reconnect_interval == 15
    assert cfg.global_.api_port == 9090
    assert len(cfg.endpoints) == 1
    assert cfg.endpoints[0].name == "my-server"
    assert len(cfg.tunnels) == 1
    assert cfg.tunnels[0].subdomain == "web"


def test_env_interpolation(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_TOKEN", "secret123")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
telegram:
  bot_token: "${TEST_TOKEN}"
  chat_id: "12345"
  enabled: true
""")
    cfg = load_config(config_file)
    assert cfg.telegram.bot_token == "secret123"
    assert cfg.telegram.chat_id == "12345"


def test_env_interpolation_missing(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
telegram:
  bot_token: "${NONEXISTENT_VAR}"
""")
    cfg = load_config(config_file)
    # Should keep the original placeholder when env var is missing
    assert cfg.telegram.bot_token == "${NONEXISTENT_VAR}"


def test_empty_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    cfg = load_config(config_file)
    assert cfg.global_.reconnect_interval == 30  # default
    assert len(cfg.endpoints) == 0
    assert len(cfg.tunnels) == 0


def test_defaults():
    cfg = AppConfig.model_validate({})
    assert cfg.global_.reconnect_interval == 30
    assert cfg.global_.api_port == 8080
    assert cfg.telegram.enabled is False


def test_tunnel_endpoints_default():
    cfg = AppConfig.model_validate({
        "tunnels": [
            {
                "name": "test",
                "internal_host": "192.168.1.1",
                "internal_port": 22,
                "remote_port": 2222,
            }
        ]
    })
    # Empty endpoints list means "all endpoints"
    assert cfg.tunnels[0].endpoints == []
    assert cfg.tunnels[0].protocol == "tcp"
