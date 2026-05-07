from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter(tags=["web"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Production login page (Phase 5.1). Anonymous access; client-side
    redirect to ?next= on success or to / by default."""
    return templates.TemplateResponse(request=request, name="login.html")


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request=request, name="chat.html")


@router.get("/qa", response_class=HTMLResponse)
async def qa_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/self-check", response_class=HTMLResponse)
async def selfcheck_page(request: Request):
    return templates.TemplateResponse(request=request, name="selfcheck.html")


@router.get("/self-check/history", response_class=HTMLResponse)
async def selfcheck_history_page(request: Request):
    return templates.TemplateResponse(request=request, name="history.html")


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")


@router.get("/_/styleguide", response_class=HTMLResponse)
async def styleguide_page(request: Request):
    """Internal design-system showcase. No auth gate — page is harmless,
    but kept on `_/` prefix to signal internal use."""
    return templates.TemplateResponse(request=request, name="_styleguide.html")


@router.get("/eval", response_class=HTMLResponse)
async def eval_page(request: Request):
    """Eval dashboard (Phase 5.2). HTML shell renders for anyone; the
    actual data API at /eval/dashboard requires super-admin. Page-side JS
    detects 403 and shows a friendly state."""
    return templates.TemplateResponse(request=request, name="eval.html")


@router.get("/supervisor", response_class=HTMLResponse)
async def supervisor_page(request: Request):
    """Supervisor dashboard (Phase 5.5). Per-topic aggregates + students
    list with privacy mask. Data fetched client-side from
    /tenants/{slug}/supervisor/* using the tenant_slug from /me."""
    return templates.TemplateResponse(request=request, name="supervisor.html")


@router.get("/tenant-admin", response_class=HTMLResponse)
async def tenant_admin_page(request: Request):
    """Tenant-admin dashboard (Phase 5.6). Program + coverage + invites
    + users list. Data fetched client-side from /tenants/{slug}/program,
    /tenants/{slug}/coverage, /invites, /tenants/{slug}/supervisor/students."""
    return templates.TemplateResponse(request=request, name="tenant_admin.html")


# Phase 3 wireframes — internal previews of redesigned screens.
# All under /_/wf/* prefix, no auth, hard-coded sample data.
# Will be deleted at end of Phase 5 once production templates are migrated.
@router.get("/_/wf/chat", response_class=HTMLResponse)
async def wf_chat(request: Request):
    return templates.TemplateResponse(request=request, name="wf/chat.html")


@router.get("/_/wf/refusal", response_class=HTMLResponse)
async def wf_refusal(request: Request):
    return templates.TemplateResponse(request=request, name="wf/refusal.html")


@router.get("/_/wf/eval", response_class=HTMLResponse)
async def wf_eval(request: Request):
    return templates.TemplateResponse(request=request, name="wf/eval.html")


@router.get("/_/wf/selfcheck", response_class=HTMLResponse)
async def wf_selfcheck(request: Request):
    return templates.TemplateResponse(request=request, name="wf/selfcheck.html")


@router.get("/_/wf/supervisor", response_class=HTMLResponse)
async def wf_supervisor(request: Request):
    return templates.TemplateResponse(request=request, name="wf/supervisor.html")


@router.get("/_/wf/tenant-admin", response_class=HTMLResponse)
async def wf_tenant_admin(request: Request):
    return templates.TemplateResponse(request=request, name="wf/tenant-admin.html")


@router.get("/_/wf/login", response_class=HTMLResponse)
async def wf_login(request: Request):
    return templates.TemplateResponse(request=request, name="wf/login.html")
