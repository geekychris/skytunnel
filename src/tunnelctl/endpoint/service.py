"""Endpoint service - monitors tunnels and manages reverse proxy config on the public server."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tunnelctl.config import AppConfig
    from tunnelctl.state import StateStore

logger = logging.getLogger(__name__)


class EndpointService:
    """Runs on the public-facing server. Monitors which tunnel ports are active
    and regenerates reverse proxy config when tunnels come up or go down."""

    def __init__(self, config: AppConfig, state: StateStore) -> None:
        self.config = config
        self.state = state
        self._active_ports: set[int] = set()

    def _get_proxy_generator(self, endpoint_config):
        """Get the appropriate config generator based on proxy type."""
        if endpoint_config.proxy.type == "caddy":
            from tunnelctl.endpoint.caddy import CaddyConfigGenerator

            return CaddyConfigGenerator(endpoint_config)
        else:
            from tunnelctl.endpoint.nginx import NginxConfigGenerator

            return NginxConfigGenerator(endpoint_config)

    def _check_port(self, port: int) -> bool:
        """Check if a port is listening on localhost."""
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except (ConnectionRefusedError, OSError, TimeoutError):
            return False

    async def _scan_ports(self) -> set[int]:
        """Check all configured tunnel remote ports."""
        active = set()
        loop = asyncio.get_event_loop()
        for tunnel in self.config.tunnels:
            is_up = await loop.run_in_executor(None, self._check_port, tunnel.remote_port)
            if is_up:
                active.add(tunnel.remote_port)
        return active

    async def _update_proxy_config(self) -> None:
        """Regenerate and apply proxy config for all endpoints on this server."""
        for ep in self.config.endpoints:
            generator = self._get_proxy_generator(ep)
            # Only include tunnels whose ports are actually active
            active_tunnels = [
                t for t in self.config.tunnels if t.remote_port in self._active_ports
            ]
            generator.apply(active_tunnels)

    async def run(self) -> None:
        """Main monitoring loop."""
        logger.info("Endpoint service starting, monitoring %d tunnel port(s)", len(self.config.tunnels))

        # Initial proxy config
        self._active_ports = await self._scan_ports()
        await self._update_proxy_config()
        await self.state.append_log(
            "INFO", f"Endpoint service started, {len(self._active_ports)} active port(s)"
        )

        while True:
            await asyncio.sleep(self.config.global_.health_check_interval)

            new_active = await self._scan_ports()
            if new_active != self._active_ports:
                added = new_active - self._active_ports
                removed = self._active_ports - new_active

                for port in added:
                    tunnel = next(
                        (t for t in self.config.tunnels if t.remote_port == port), None
                    )
                    name = tunnel.name if tunnel else str(port)
                    logger.info("Tunnel port %d (%s) came up", port, name)
                    await self.state.append_log("INFO", f"Port {port} ({name}) came up")

                for port in removed:
                    tunnel = next(
                        (t for t in self.config.tunnels if t.remote_port == port), None
                    )
                    name = tunnel.name if tunnel else str(port)
                    logger.warning("Tunnel port %d (%s) went down", port, name)
                    await self.state.append_log("WARNING", f"Port {port} ({name}) went down")

                self._active_ports = new_active
                await self._update_proxy_config()
