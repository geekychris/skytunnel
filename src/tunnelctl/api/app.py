"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tunnelctl.api.routes import config as config_routes
from tunnelctl.api.routes import endpoints as endpoint_routes
from tunnelctl.api.routes import status as status_routes
from tunnelctl.api.routes import tunnels as tunnel_routes

if TYPE_CHECKING:
    from tunnelctl.agent.manager import TunnelManager
    from tunnelctl.config import AppConfig
    from tunnelctl.state import StateStore

WEB_DIR = Path(__file__).parent.parent / "web"


class AppState:
    """Shared application state accessible from route handlers."""

    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        state: StateStore,
        manager: TunnelManager | None = None,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.state = state
        self.manager = manager
        self.templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def create_app(
    config: AppConfig,
    config_path: Path,
    state: StateStore,
    manager: TunnelManager | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app_state = AppState(config, config_path, state, manager)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="tunnelctl",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.tunnelctl = app_state

    # Mount static files
    static_dir = WEB_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include API routes
    app.include_router(status_routes.router, prefix="/api")
    app.include_router(tunnel_routes.router, prefix="/api")
    app.include_router(endpoint_routes.router, prefix="/api")
    app.include_router(config_routes.router, prefix="/api")

    # Web UI routes
    from tunnelctl.api.routes import web as web_routes

    app.include_router(web_routes.router)

    return app
