"""Web UI routes serving Jinja2 templates."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["web"])


@router.get("/")
async def dashboard(request: Request):
    app_state = request.app.state.tunnelctl
    return app_state.templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/tunnels")
async def tunnels_page(request: Request):
    app_state = request.app.state.tunnelctl
    return app_state.templates.TemplateResponse("tunnels.html", {"request": request})


@router.get("/logs")
async def logs_page(request: Request):
    app_state = request.app.state.tunnelctl
    return app_state.templates.TemplateResponse("logs.html", {"request": request})
