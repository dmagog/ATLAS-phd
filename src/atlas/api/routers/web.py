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
