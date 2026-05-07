from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter(tags=["web"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Production login page. Anonymous access; client-side
    redirect to ?next= on success or to / by default."""
    return templates.TemplateResponse(request=request, name="login.html")


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat (Q&A + self-check via planner)."""
    return templates.TemplateResponse(request=request, name="chat.html")


@router.get("/self-check", response_class=HTMLResponse)
async def selfcheck_page(request: Request):
    return templates.TemplateResponse(request=request, name="selfcheck.html")


@router.get("/self-check/history", response_class=HTMLResponse)
async def selfcheck_history_page(request: Request):
    return templates.TemplateResponse(request=request, name="history.html")


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Materials upload/list (tenant-admin / super-admin)."""
    return templates.TemplateResponse(request=request, name="admin.html")


@router.get("/eval", response_class=HTMLResponse)
async def eval_page(request: Request):
    """Eval dashboard. Data API at /eval/dashboard requires super-admin."""
    return templates.TemplateResponse(request=request, name="eval.html")


@router.get("/supervisor", response_class=HTMLResponse)
async def supervisor_page(request: Request):
    """Supervisor dashboard. Per-topic aggregates + students list with
    privacy mask. Data fetched from /tenants/{slug}/supervisor/*."""
    return templates.TemplateResponse(request=request, name="supervisor.html")


@router.get("/tenant-admin", response_class=HTMLResponse)
async def tenant_admin_page(request: Request):
    """Tenant-admin dashboard. Program + coverage + invites + users."""
    return templates.TemplateResponse(request=request, name="tenant_admin.html")


@router.get("/_/styleguide", response_class=HTMLResponse)
async def styleguide_page(request: Request):
    """Internal design-system showcase. No auth gate — page is harmless,
    but kept on `_/` prefix to signal internal use."""
    return templates.TemplateResponse(request=request, name="_styleguide.html")
