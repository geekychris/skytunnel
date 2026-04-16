"""Health checker - periodic tunnel health monitoring and alerting."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Coroutine

if TYPE_CHECKING:
    from tunnelctl.agent.manager import TunnelManager
    from tunnelctl.config import GlobalConfig
    from tunnelctl.state import StateStore

logger = logging.getLogger(__name__)

# Type for alert callback: async def callback(tunnel_key, old_status, new_status)
AlertCallback = Callable[[str, str, str], Coroutine]


class HealthChecker:
    """Periodically checks tunnel health and triggers alerts on state changes."""

    def __init__(
        self,
        manager: TunnelManager,
        global_config: GlobalConfig,
        state: StateStore,
        on_alert: AlertCallback | None = None,
    ) -> None:
        self.manager = manager
        self.config = global_config
        self.state = state
        self.on_alert = on_alert
        self._task: asyncio.Task | None = None
        self._previous_health: dict[str, bool] = {}

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="health-checker")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                await self._check_all()
            except Exception:
                logger.exception("Health check iteration failed")
            await asyncio.sleep(self.config.health_check_interval)

    async def _check_all(self) -> None:
        for key, tunnel in self.manager._tunnels.items():
            try:
                healthy = await asyncio.wait_for(
                    tunnel.health_check(),
                    timeout=self.config.health_check_timeout,
                )
            except asyncio.TimeoutError:
                healthy = False

            was_healthy = self._previous_health.get(key)
            self._previous_health[key] = healthy

            # Detect state transitions
            if was_healthy is not None and was_healthy != healthy:
                new_status = "connected" if healthy else "disconnected"
                old_status = "connected" if was_healthy else "disconnected"
                logger.warning(
                    "Tunnel %s health changed: %s -> %s", key, old_status, new_status
                )
                await self.state.append_log(
                    "WARNING",
                    f"Health changed: {old_status} -> {new_status}",
                    key.split("@")[0],
                )
                if self.on_alert:
                    try:
                        await self.on_alert(key, old_status, new_status)
                    except Exception:
                        logger.exception("Alert callback failed for %s", key)

        # Clean up entries for tunnels that no longer exist
        current_keys = set(self.manager._tunnels.keys())
        for stale_key in list(self._previous_health.keys()):
            if stale_key not in current_keys:
                del self._previous_health[stale_key]
