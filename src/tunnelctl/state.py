"""Async SQLite state store for tunnel statuses and logs."""

from __future__ import annotations

import time
from dataclasses import dataclass

import aiosqlite


@dataclass
class TunnelStatus:
    endpoint: str
    tunnel: str
    status: str  # connecting, connected, disconnected, error
    error: str | None = None
    last_connected: float | None = None
    updated_at: float = 0.0


@dataclass
class LogEntry:
    timestamp: float
    level: str
    message: str
    tunnel: str | None = None


class StateStore:
    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None

    async def init(self, db_path: str = ":memory:") -> None:
        self._db = await aiosqlite.connect(db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS tunnel_status (
                endpoint TEXT,
                tunnel TEXT,
                status TEXT DEFAULT 'disconnected',
                error TEXT,
                last_connected REAL,
                updated_at REAL,
                PRIMARY KEY (endpoint, tunnel)
            );
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                level TEXT,
                message TEXT,
                tunnel TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
        """)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "StateStore not initialized"
        return self._db

    async def set_tunnel_status(
        self,
        endpoint: str,
        tunnel: str,
        status: str,
        error: str | None = None,
    ) -> None:
        now = time.time()
        last_connected = now if status == "connected" else None
        await self.db.execute(
            """INSERT INTO tunnel_status (endpoint, tunnel, status, error, last_connected, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(endpoint, tunnel) DO UPDATE SET
                 status = excluded.status,
                 error = excluded.error,
                 last_connected = COALESCE(excluded.last_connected, last_connected),
                 updated_at = excluded.updated_at""",
            (endpoint, tunnel, status, error, last_connected, now),
        )
        await self.db.commit()

    async def get_all_statuses(self) -> list[TunnelStatus]:
        cursor = await self.db.execute(
            "SELECT endpoint, tunnel, status, error, last_connected, updated_at FROM tunnel_status"
        )
        rows = await cursor.fetchall()
        return [
            TunnelStatus(
                endpoint=r[0],
                tunnel=r[1],
                status=r[2],
                error=r[3],
                last_connected=r[4],
                updated_at=r[5],
            )
            for r in rows
        ]

    async def get_endpoint_statuses(self, endpoint: str) -> list[TunnelStatus]:
        cursor = await self.db.execute(
            "SELECT endpoint, tunnel, status, error, last_connected, updated_at "
            "FROM tunnel_status WHERE endpoint = ?",
            (endpoint,),
        )
        rows = await cursor.fetchall()
        return [
            TunnelStatus(
                endpoint=r[0],
                tunnel=r[1],
                status=r[2],
                error=r[3],
                last_connected=r[4],
                updated_at=r[5],
            )
            for r in rows
        ]

    async def append_log(
        self, level: str, message: str, tunnel: str | None = None
    ) -> None:
        await self.db.execute(
            "INSERT INTO logs (timestamp, level, message, tunnel) VALUES (?, ?, ?, ?)",
            (time.time(), level, message, tunnel),
        )
        await self.db.commit()

    async def get_logs(
        self, limit: int = 100, tunnel: str | None = None
    ) -> list[LogEntry]:
        if tunnel:
            cursor = await self.db.execute(
                "SELECT timestamp, level, message, tunnel FROM logs "
                "WHERE tunnel = ? ORDER BY timestamp DESC LIMIT ?",
                (tunnel, limit),
            )
        else:
            cursor = await self.db.execute(
                "SELECT timestamp, level, message, tunnel FROM logs "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [
            LogEntry(timestamp=r[0], level=r[1], message=r[2], tunnel=r[3])
            for r in rows
        ]
