from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["demo"])

_STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"


def _render_template(request: Request, template_name: str) -> HTMLResponse:
    html = (_STATIC_ROOT / template_name).read_text(encoding="utf-8")
    html = html.replace("__CAMO_API_PREFIX__", request.app.state.settings.api_v1_prefix)
    html = html.replace("__CAMO_QUERY__", request.url.query)
    return HTMLResponse(content=html)


@router.get("/demo", response_class=HTMLResponse)
async def demo_hub_page(request: Request) -> HTMLResponse:
    return _render_template(request, "demo-hub.html")


@router.get("/demo/portrait", response_class=HTMLResponse)
async def demo_portrait_page(request: Request) -> HTMLResponse:
    return _render_template(request, "demo-portrait.html")


@router.get("/demo/chat", response_class=HTMLResponse)
async def demo_chat_page(request: Request) -> HTMLResponse:
    return _render_template(request, "demo-chat.html")
