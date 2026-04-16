"""CLI commands that talk to the tunnelctl API."""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

console = Console()


async def cmd_status(api_url: str, endpoint_name: str | None = None) -> None:
    """Display tunnel statuses in a table."""
    url = f"{api_url}/api/status"
    if endpoint_name:
        url = f"{api_url}/api/status/{endpoint_name}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            console.print(f"[red]Error: {resp.text}[/red]")
            return
        statuses = resp.json()

    if not statuses:
        console.print("[dim]No tunnels found.[/dim]")
        return

    table = Table(title="Tunnel Status")
    table.add_column("Tunnel", style="cyan")
    table.add_column("Endpoint", style="blue")
    table.add_column("Status")
    table.add_column("Last Connected", style="dim")
    table.add_column("Error", style="red")

    status_colors = {
        "connected": "green",
        "connecting": "yellow",
        "disconnected": "red",
        "error": "red bold",
    }

    for s in statuses:
        color = status_colors.get(s["status"], "white")
        last_conn = ""
        if s.get("last_connected"):
            dt = datetime.datetime.fromtimestamp(s["last_connected"])
            last_conn = dt.strftime("%Y-%m-%d %H:%M:%S")

        table.add_row(
            s["tunnel"],
            s["endpoint"],
            f"[{color}]{s['status']}[/{color}]",
            last_conn,
            s.get("error") or "",
        )

    console.print(table)


async def cmd_tunnels(
    action: str,
    api_url: str,
    name: str | None = None,
    internal_host: str | None = None,
    internal_port: int | None = None,
    remote_port: int | None = None,
    protocol: str = "tcp",
    endpoints: list[str] | None = None,
    subdomain: str | None = None,
) -> None:
    """Manage tunnel definitions."""
    async with httpx.AsyncClient() as client:
        if action == "list":
            resp = await client.get(f"{api_url}/api/tunnels")
            tunnels = resp.json()
            table = Table(title="Configured Tunnels")
            table.add_column("Name", style="cyan")
            table.add_column("Internal", style="blue")
            table.add_column("Remote Port", style="green")
            table.add_column("Protocol")
            table.add_column("Endpoints")
            table.add_column("Subdomain", style="dim")

            for t in tunnels:
                table.add_row(
                    t["name"],
                    f"{t['internal_host']}:{t['internal_port']}",
                    str(t["remote_port"]),
                    t["protocol"],
                    ", ".join(t.get("endpoints", [])) or "all",
                    t.get("subdomain") or "-",
                )
            console.print(table)

        elif action == "add":
            if not all([name, internal_host, internal_port, remote_port]):
                console.print("[red]Required: --name, --host, --port, --remote-port[/red]")
                return
            payload = {
                "name": name,
                "internal_host": internal_host,
                "internal_port": internal_port,
                "remote_port": remote_port,
                "protocol": protocol,
                "endpoints": endpoints or [],
                "subdomain": subdomain,
            }
            resp = await client.post(f"{api_url}/api/tunnels", json=payload)
            if resp.status_code == 200:
                console.print(f"[green]{resp.json()['message']}[/green]")
            else:
                console.print(f"[red]Error: {resp.text}[/red]")

        elif action == "remove":
            if not name:
                console.print("[red]Required: --name[/red]")
                return
            resp = await client.delete(f"{api_url}/api/tunnels/{name}")
            if resp.status_code == 200:
                console.print(f"[green]{resp.json()['message']}[/green]")
            else:
                console.print(f"[red]Error: {resp.text}[/red]")

        else:
            console.print(f"[red]Unknown action: {action}. Use list, add, or remove.[/red]")


async def cmd_check(config_path: Path) -> None:
    """Verify SSH connectivity to all configured endpoints."""
    import asyncssh

    from tunnelctl.config import load_config

    cfg = load_config(config_path)

    for ep in cfg.endpoints:
        console.print(f"Checking [cyan]{ep.name}[/cyan] ({ep.host}:{ep.port})...", end=" ")
        try:
            key_path = ep.key_file.replace("~", str(Path.home()))
            conn = await asyncssh.connect(
                ep.host,
                port=ep.port,
                username=ep.user,
                client_keys=[key_path],
                known_hosts=None,
                login_timeout=10,
            )
            conn.close()
            console.print("[green]OK[/green]")
        except Exception as e:
            console.print(f"[red]FAILED: {e}[/red]")


async def cmd_reload(api_url: str) -> None:
    """Reload agent configuration."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{api_url}/api/config/reload")
        if resp.status_code == 200:
            data = resp.json()
            console.print(f"[green]{data['message']} ({data['tunnels']} tunnels)[/green]")
        else:
            console.print(f"[red]Error: {resp.text}[/red]")


async def cmd_logs(api_url: str, limit: int = 50, tunnel: str | None = None) -> None:
    """Display recent logs."""
    async with httpx.AsyncClient() as client:
        params: dict = {"limit": limit}
        if tunnel:
            params["tunnel"] = tunnel
        resp = await client.get(f"{api_url}/api/logs", params=params)
        if resp.status_code != 200:
            console.print(f"[red]Error: {resp.text}[/red]")
            return
        logs = resp.json()

    if not logs:
        console.print("[dim]No logs found.[/dim]")
        return

    level_colors = {"INFO": "green", "WARNING": "yellow", "ERROR": "red"}
    for log in reversed(logs):  # oldest first
        dt = datetime.datetime.fromtimestamp(log["timestamp"])
        color = level_colors.get(log["level"], "white")
        tunnel_tag = f" [{log['tunnel']}]" if log.get("tunnel") else ""
        console.print(
            f"[dim]{dt.strftime('%H:%M:%S')}[/dim] "
            f"[{color}]{log['level']:>7}[/{color}]"
            f"{tunnel_tag} {log['message']}"
        )
