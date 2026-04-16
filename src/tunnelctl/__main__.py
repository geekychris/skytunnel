"""Entry point for tunnelctl."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import typer
import uvicorn

from tunnelctl.config import load_config

app = typer.Typer(name="tunnelctl", help="Reverse tunnel management service")

DEFAULT_CONFIG = "config.yaml"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@app.command()
def agent(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Config file path"),
) -> None:
    """Run the tunnel agent (main daemon: tunnels + API + web UI)."""
    asyncio.run(_run_agent(Path(config)))


async def _run_agent(config_path: Path) -> None:
    from tunnelctl.agent.health import HealthChecker
    from tunnelctl.agent.manager import TunnelManager
    from tunnelctl.api.app import create_app
    from tunnelctl.state import StateStore

    cfg = load_config(config_path)
    setup_logging(cfg.global_.log_level)
    logger = logging.getLogger("tunnelctl")

    # Initialize state store
    state = StateStore()
    await state.init(cfg.global_.state_db)

    # Create tunnel manager and start tunnels
    manager = TunnelManager(cfg, state)
    await manager.start_all()

    # Set up health checker with optional Telegram alerts
    alert_cb = None
    if cfg.telegram.enabled and cfg.telegram.bot_token:
        from tunnelctl.bot.telegram import create_alert_callback

        alert_cb = create_alert_callback(cfg.telegram)

    health = HealthChecker(manager, cfg.global_, state, on_alert=alert_cb)
    await health.start()

    # Optionally start Telegram bot
    bot_task = None
    if cfg.telegram.enabled and cfg.telegram.bot_token:
        from tunnelctl.bot.telegram import start_bot

        bot_task = asyncio.create_task(start_bot(cfg.telegram, state, manager))

    # Create and run FastAPI app
    fastapi_app = create_app(cfg, config_path, state, manager)
    server_config = uvicorn.Config(
        fastapi_app,
        host=cfg.global_.api_host,
        port=cfg.global_.api_port,
        log_level=cfg.global_.log_level.lower(),
    )
    server = uvicorn.Server(server_config)

    logger.info(
        "tunnelctl agent running on %s:%d", cfg.global_.api_host, cfg.global_.api_port
    )

    try:
        await server.serve()
    finally:
        logger.info("Shutting down...")
        await health.stop()
        if bot_task:
            bot_task.cancel()
        await manager.stop_all()
        await state.close()


@app.command()
def endpoint(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Config file path"),
) -> None:
    """Run the endpoint service (on the public-facing server)."""
    asyncio.run(_run_endpoint(Path(config)))


async def _run_endpoint(config_path: Path) -> None:
    from tunnelctl.endpoint.service import EndpointService
    from tunnelctl.state import StateStore

    cfg = load_config(config_path)
    setup_logging(cfg.global_.log_level)

    state = StateStore()
    await state.init(cfg.global_.state_db)

    service = EndpointService(cfg, state)
    await service.run()


@app.command()
def status(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    endpoint_name: str = typer.Option(None, "--endpoint", "-e"),
    api_url: str = typer.Option("http://localhost:8080", "--api", "-a"),
) -> None:
    """Show tunnel statuses."""
    from tunnelctl.cli.main import cmd_status

    asyncio.run(cmd_status(api_url, endpoint_name))


@app.command("tunnels")
def tunnels_cmd(
    action: str = typer.Argument("list", help="list, add, or remove"),
    name: str = typer.Option(None, "--name", "-n"),
    internal_host: str = typer.Option(None, "--host"),
    internal_port: int = typer.Option(None, "--port"),
    remote_port: int = typer.Option(None, "--remote-port"),
    protocol: str = typer.Option("tcp", "--protocol"),
    endpoints: str = typer.Option("", "--endpoints", help="Comma-separated endpoint names"),
    subdomain: str = typer.Option(None, "--subdomain"),
    api_url: str = typer.Option("http://localhost:8080", "--api", "-a"),
) -> None:
    """Manage tunnel definitions."""
    from tunnelctl.cli.main import cmd_tunnels

    ep_list = [e.strip() for e in endpoints.split(",") if e.strip()] if endpoints else []
    asyncio.run(
        cmd_tunnels(
            action, api_url, name, internal_host, internal_port,
            remote_port, protocol, ep_list, subdomain,
        )
    )


@app.command()
def check(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Verify SSH connectivity to all endpoints."""
    from tunnelctl.cli.main import cmd_check

    asyncio.run(cmd_check(Path(config)))


@app.command()
def reload(
    api_url: str = typer.Option("http://localhost:8080", "--api", "-a"),
) -> None:
    """Reload the agent configuration."""
    from tunnelctl.cli.main import cmd_reload

    asyncio.run(cmd_reload(api_url))


@app.command()
def logs(
    limit: int = typer.Option(50, "--limit", "-l"),
    tunnel: str = typer.Option(None, "--tunnel", "-t"),
    api_url: str = typer.Option("http://localhost:8080", "--api", "-a"),
) -> None:
    """View recent logs."""
    from tunnelctl.cli.main import cmd_logs

    asyncio.run(cmd_logs(api_url, limit, tunnel))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
