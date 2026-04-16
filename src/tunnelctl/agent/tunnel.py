"""SingleTunnel - manages one asyncssh reverse tunnel to one endpoint."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import asyncssh

if TYPE_CHECKING:
    from tunnelctl.config import EndpointConfig, GlobalConfig, TunnelConfig
    from tunnelctl.state import StateStore

logger = logging.getLogger(__name__)


class SingleTunnel:
    """One reverse SSH tunnel: forwards a single port through one endpoint."""

    def __init__(
        self,
        tunnel_config: TunnelConfig,
        endpoint_config: EndpointConfig,
        global_config: GlobalConfig,
        state: StateStore,
    ) -> None:
        self.tunnel = tunnel_config
        self.endpoint = endpoint_config
        self.global_config = global_config
        self.state = state
        self._conn: asyncssh.SSHClientConnection | None = None
        self._listener: asyncssh.SSHListener | None = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def label(self) -> str:
        return f"{self.tunnel.name}@{self.endpoint.name}"

    async def start(self) -> None:
        """Start the tunnel with auto-reconnect loop."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name=f"tunnel-{self.label}")

    async def stop(self) -> None:
        """Gracefully stop the tunnel."""
        self._stop_event.set()
        await self._disconnect()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.state.set_tunnel_status(
            self.endpoint.name, self.tunnel.name, "disconnected"
        )

    async def _run_loop(self) -> None:
        """Reconnect loop with exponential backoff."""
        backoff = 1
        max_backoff = self.global_config.reconnect_interval

        while not self._stop_event.is_set():
            try:
                await self._connect()
                backoff = 1  # reset on successful connect
                # Wait until connection drops or stop is requested
                await self._wait_for_disconnect()
            except asyncssh.Error as e:
                error_msg = str(e)
                logger.error("SSH error for %s: %s", self.label, error_msg)
                await self.state.set_tunnel_status(
                    self.endpoint.name, self.tunnel.name, "error", error=error_msg
                )
                await self.state.append_log(
                    "ERROR", f"SSH error: {error_msg}", self.tunnel.name
                )
            except OSError as e:
                error_msg = str(e)
                logger.error("Connection error for %s: %s", self.label, error_msg)
                await self.state.set_tunnel_status(
                    self.endpoint.name, self.tunnel.name, "error", error=error_msg
                )
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                logger.exception("Unexpected error for %s", self.label)
                await self.state.set_tunnel_status(
                    self.endpoint.name, self.tunnel.name, "error", error=error_msg
                )
                await self.state.append_log(
                    "ERROR", f"Unexpected: {error_msg}", self.tunnel.name
                )

            await self._disconnect()

            if self._stop_event.is_set():
                break

            await self.state.set_tunnel_status(
                self.endpoint.name, self.tunnel.name, "disconnected"
            )
            logger.info("Reconnecting %s in %ds...", self.label, backoff)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                break  # stop was requested during backoff
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, max_backoff)

    async def _connect(self) -> None:
        """Establish SSH connection and create reverse forward."""
        await self.state.set_tunnel_status(
            self.endpoint.name, self.tunnel.name, "connecting"
        )
        logger.info("Connecting %s -> %s:%d", self.label, self.endpoint.host, self.endpoint.port)

        key_path = self.endpoint.key_file.replace("~", str(Path.home()))

        self._conn = await asyncssh.connect(
            self.endpoint.host,
            port=self.endpoint.port,
            username=self.endpoint.user,
            client_keys=[key_path],
            known_hosts=None,  # TODO: proper host key verification
            keepalive_interval=30,
            keepalive_count_max=3,
        )

        self._listener = await self._conn.forward_remote_port(
            "",
            self.tunnel.remote_port,
            self.tunnel.internal_host,
            self.tunnel.internal_port,
        )

        await self.state.set_tunnel_status(
            self.endpoint.name, self.tunnel.name, "connected"
        )
        await self.state.append_log(
            "INFO",
            f"Connected: {self.tunnel.internal_host}:{self.tunnel.internal_port} "
            f"-> {self.endpoint.name}:{self.tunnel.remote_port}",
            self.tunnel.name,
        )
        logger.info("Tunnel %s established on remote port %d", self.label, self.tunnel.remote_port)

    async def _wait_for_disconnect(self) -> None:
        """Wait until the SSH connection closes or stop is requested."""
        if not self._conn:
            return
        # asyncssh connection has a wait_closed() coroutine
        disconnect_task = asyncio.create_task(self._conn.wait_closed())
        stop_task = asyncio.create_task(self._stop_event.wait())
        done, pending = await asyncio.wait(
            {disconnect_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def _disconnect(self) -> None:
        """Close SSH connection and listener."""
        if self._listener:
            self._listener.close()
            self._listener = None
        if self._conn:
            self._conn.close()
            try:
                await asyncio.wait_for(self._conn.wait_closed(), timeout=5)
            except (asyncio.TimeoutError, Exception):
                pass
            self._conn = None

    async def health_check(self) -> bool:
        """Check if the tunnel is alive by verifying the connection is open."""
        if not self._conn:
            return False
        try:
            # Simple check: is the transport still open?
            return self._conn.is_connected() if hasattr(self._conn, "is_connected") else not self._conn._transport.is_closing()
        except Exception:
            return False
