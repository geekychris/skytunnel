"""Configuration loading and Pydantic models."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def _interpolate_env(value: str) -> str:
    """Replace ${ENV_VAR} patterns with environment variable values."""
    return re.sub(
        r"\$\{([^}]+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        value,
    )


def _interpolate_recursive(obj: object) -> object:
    """Recursively interpolate environment variables in config data."""
    if isinstance(obj, str):
        return _interpolate_env(obj)
    if isinstance(obj, dict):
        return {k: _interpolate_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate_recursive(item) for item in obj]
    return obj


class GlobalConfig(BaseModel):
    reconnect_interval: int = 30
    health_check_interval: int = 60
    health_check_timeout: int = 10
    log_level: str = "INFO"
    state_db: str = "./tunnelctl.db"
    api_port: int = 8080
    api_host: str = "0.0.0.0"


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""
    alert_on_disconnect: bool = True
    alert_on_reconnect: bool = True
    enabled: bool = False


class ProxyConfig(BaseModel):
    type: str = "nginx"  # "nginx" or "caddy"
    http_domain: str = ""
    ssl: bool = True
    config_path: str = "/etc/nginx/conf.d/tunnelctl.conf"
    reload_command: str = "nginx -s reload"


class EndpointConfig(BaseModel):
    name: str
    host: str
    port: int = 22
    user: str = "tunnel"
    key_file: str = "~/.ssh/tunnel_key"
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)


class TunnelConfig(BaseModel):
    name: str
    internal_host: str
    internal_port: int
    remote_port: int
    protocol: str = "tcp"  # "tcp" or "http"
    endpoints: list[str] = Field(default_factory=list)  # empty = all endpoints
    subdomain: str | None = None


class AppConfig(BaseModel):
    global_: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    endpoints: list[EndpointConfig] = Field(default_factory=list)
    tunnels: list[TunnelConfig] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


def load_config(path: str | Path) -> AppConfig:
    """Load and validate configuration from a YAML file."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    interpolated = _interpolate_recursive(raw)
    return AppConfig.model_validate(interpolated)


def reload_config(path: str | Path, current: AppConfig) -> AppConfig:
    """Reload configuration, returning the new config."""
    return load_config(path)
