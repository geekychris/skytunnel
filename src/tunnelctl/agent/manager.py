"""TunnelManager - orchestrates all tunnels to all endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tunnelctl.agent.tunnel import SingleTunnel

if TYPE_CHECKING:
    from tunnelctl.config import AppConfig
    from tunnelctl.state import StateStore

logger = logging.getLogger(__name__)


class TunnelManager:
    """Creates and manages SingleTunnel instances for each (tunnel, endpoint) pair."""

    def __init__(self, config: AppConfig, state: StateStore) -> None:
        self.config = config
        self.state = state
        self._tunnels: dict[str, SingleTunnel] = {}  # key: "tunnel_name@endpoint_name"

    def _build_tunnel_key(self, tunnel_name: str, endpoint_name: str) -> str:
        return f"{tunnel_name}@{endpoint_name}"

    def _get_endpoints_for_tunnel(self, tunnel_endpoint_names: list[str]) -> list[str]:
        """Resolve which endpoints a tunnel targets. Empty list = all endpoints."""
        all_endpoint_names = [ep.name for ep in self.config.endpoints]
        if not tunnel_endpoint_names:
            return all_endpoint_names
        return [name for name in tunnel_endpoint_names if name in all_endpoint_names]

    def _endpoint_by_name(self, name: str):
        for ep in self.config.endpoints:
            if ep.name == name:
                return ep
        return None

    async def start_all(self) -> None:
        """Start all configured tunnels."""
        for tc in self.config.tunnels:
            endpoint_names = self._get_endpoints_for_tunnel(tc.endpoints)
            for ep_name in endpoint_names:
                ep = self._endpoint_by_name(ep_name)
                if not ep:
                    logger.warning("Endpoint %s not found for tunnel %s", ep_name, tc.name)
                    continue
                key = self._build_tunnel_key(tc.name, ep_name)
                if key in self._tunnels:
                    continue
                st = SingleTunnel(tc, ep, self.config.global_, self.state)
                self._tunnels[key] = st
                await st.start()
                logger.info("Started tunnel %s", key)

        await self.state.append_log("INFO", f"Started {len(self._tunnels)} tunnel(s)")

    async def stop_all(self) -> None:
        """Stop all running tunnels."""
        for key, st in self._tunnels.items():
            logger.info("Stopping tunnel %s", key)
            await st.stop()
        self._tunnels.clear()
        await self.state.append_log("INFO", "All tunnels stopped")

    async def add_tunnel(self, tunnel_name: str) -> list[str]:
        """Start tunnels for a newly added tunnel config. Returns keys of started tunnels."""
        tc = next((t for t in self.config.tunnels if t.name == tunnel_name), None)
        if not tc:
            raise ValueError(f"Tunnel {tunnel_name} not found in config")

        started = []
        endpoint_names = self._get_endpoints_for_tunnel(tc.endpoints)
        for ep_name in endpoint_names:
            ep = self._endpoint_by_name(ep_name)
            if not ep:
                continue
            key = self._build_tunnel_key(tc.name, ep_name)
            if key in self._tunnels:
                continue
            st = SingleTunnel(tc, ep, self.config.global_, self.state)
            self._tunnels[key] = st
            await st.start()
            started.append(key)

        return started

    async def remove_tunnel(self, tunnel_name: str) -> list[str]:
        """Stop and remove all tunnel instances for a given tunnel name."""
        removed = []
        keys_to_remove = [k for k in self._tunnels if k.startswith(f"{tunnel_name}@")]
        for key in keys_to_remove:
            await self._tunnels[key].stop()
            del self._tunnels[key]
            removed.append(key)
        return removed

    async def reload(self, new_config: AppConfig) -> None:
        """Reload configuration: stop removed tunnels, start new ones."""
        old_keys = set(self._tunnels.keys())

        # Build the set of keys the new config wants
        new_keys: set[str] = set()
        for tc in new_config.tunnels:
            all_ep_names = [ep.name for ep in new_config.endpoints]
            ep_names = tc.endpoints if tc.endpoints else all_ep_names
            for ep_name in ep_names:
                if ep_name in all_ep_names:
                    new_keys.add(self._build_tunnel_key(tc.name, ep_name))

        # Stop tunnels no longer in config
        for key in old_keys - new_keys:
            await self._tunnels[key].stop()
            del self._tunnels[key]
            logger.info("Removed tunnel %s", key)

        # Update config reference
        self.config = new_config

        # Start new tunnels
        for key in new_keys - old_keys:
            tunnel_name, ep_name = key.split("@", 1)
            tc = next((t for t in new_config.tunnels if t.name == tunnel_name), None)
            ep = self._endpoint_by_name(ep_name)
            if tc and ep:
                st = SingleTunnel(tc, ep, new_config.global_, self.state)
                self._tunnels[key] = st
                await st.start()
                logger.info("Started tunnel %s", key)

        await self.state.append_log("INFO", f"Config reloaded: {len(self._tunnels)} tunnel(s) active")

    def get_tunnel_keys(self) -> list[str]:
        """Return all active tunnel keys."""
        return list(self._tunnels.keys())
