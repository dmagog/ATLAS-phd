from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter(tags=["web"])


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
