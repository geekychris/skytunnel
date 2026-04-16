# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SkyTunnel** (`tunnelctl`) — a Python reverse tunnel management service for exposing devices behind Starlink (CGNAT) to the public internet. Uses persistent outbound SSH reverse tunnels (asyncssh) from a Starlink-side agent to one or more public endpoints, which expose services via NGINX or Caddy.

## Build & Test Commands

```bash
pip install -e ".[dev]"          # Install in dev mode with test deps
python3 -m pytest tests/ -v      # Run all tests
python3 -m pytest tests/test_config.py -v  # Run a single test file
python3 -m pytest tests/test_api.py::test_list_tunnels -v  # Run a single test
ruff check src/ tests/           # Lint
mypy src/                        # Type check
```

## Running

```bash
tunnelctl agent -c config.yaml      # Start tunnel agent daemon (Starlink side)
tunnelctl endpoint -c config.yaml   # Start endpoint service (public server side)
tunnelctl status                     # Show tunnel statuses (talks to agent API)
tunnelctl tunnels list               # List configured tunnels
tunnelctl check -c config.yaml      # Verify SSH connectivity to all endpoints
```

## Architecture

Single Python package (`src/tunnelctl/`) running in different modes via subcommands:

- **`agent/`** — Core tunnel engine. `TunnelManager` creates a `SingleTunnel` (asyncssh reverse forward) for each (tunnel, endpoint) pair. A tunnel targeting 2 endpoints produces 2 SSH connections. `HealthChecker` monitors and triggers alerts.
- **`api/`** — FastAPI app serving REST API + web UI. Central bus: CLI, web dashboard, and Telegram bot all consume the same `/api/*` routes.
- **`cli/`** — Typer CLI that talks to the agent's API via httpx.
- **`web/`** — Jinja2 templates + vanilla JS dashboard. Polls `/api/status` for live updates.
- **`bot/`** — python-telegram-bot async handlers for remote management and disconnect alerts.
- **`endpoint/`** — Runs on public servers. Monitors tunnel ports, generates NGINX/Caddy reverse proxy configs via Jinja2 templates, and reloads the proxy.
- **`config.py`** — Pydantic models + YAML loader with `${ENV_VAR}` interpolation.
- **`state.py`** — Async SQLite store for tunnel statuses and logs.

## Key Design Decisions

- **Multi-endpoint replication**: Each tunnel config has an `endpoints` list. Empty means all endpoints. The manager creates N tunnel instances accordingly.
- **Config-driven**: Single YAML file defines endpoints, tunnels, and settings. API routes can add/remove tunnels and persist changes back to YAML.
- **asyncssh over subprocess SSH**: Native Python control over connections, reconnect logic, and health checking without shell process management.
