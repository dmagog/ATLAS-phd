from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from atlas.core.config import settings

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter(tags=["web"])

# Cache-busting для статики: `?v=<mtime>` на ссылках atlas.css. Без этого
# браузеры возвращающихся пользователей держат старый CSS после деплоя
# (memory/disk cache игнорирует etag при «свежем» эвристическом кеше).
# Колбэк, а не константа — чтобы в dev (--reload не следит за static/)
# версия обновлялась без рестарта приложения.
_STATIC_DIR = Path(__file__).parent.parent.parent / "static"


def _asset_version(filename: str = "atlas.css") -> str:
    try:
        return str(int((_STATIC_DIR / filename).stat().st_mtime))
    except OSError:
        return "0"


templates.env.globals["asset_v"] = _asset_version


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


@router.get("/_/tenants", response_class=HTMLResponse)
async def tenants_page(request: Request):
    """Super-admin tenant list page. URL uses /_/ prefix to avoid
    collision with `GET /tenants` API endpoint (returns JSON list)."""
    return templates.TemplateResponse(request=request, name="tenants.html")


@router.get("/_/invites", response_class=HTMLResponse)
async def invites_page(request: Request):
    """Dedicated invites page (tenant-admin / super-admin). URL uses /_/
    prefix to avoid collision with `/invites` API endpoint."""
    return templates.TemplateResponse(request=request, name="invites.html")


@router.get("/_/styleguide", response_class=HTMLResponse)
async def styleguide_page(request: Request):
    """Internal design-system showcase. No auth gate — page is harmless,
    but kept on `_/` prefix to signal internal use."""
    return templates.TemplateResponse(request=request, name="_styleguide.html")


@router.get("/_/demo-seed-superadmin", response_class=HTMLResponse)
async def demo_seed_superadmin_helper():
    """Phase 6 screenshot helper: idempotently creates super@optics.demo
    super-admin user (cross-tenant). Returns plain text. Disabled in
    production. Same security guard as demo-login (env != production)."""
    if getattr(settings, "app_env", "development") == "production":
        raise HTTPException(status_code=404)
    from sqlalchemy import select
    from atlas.core.security import hash_password
    from atlas.db.models import SupervisorVisibility, User, UserRole
    from atlas.db.session import AsyncSessionLocal
    import uuid as _uuid

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(User).where(User.email == "super@optics.demo")
        )).scalar_one_or_none()
        if existing is not None:
            return HTMLResponse(content=f"already exists: id={existing.id}", media_type="text/plain")
        u = User(
            id=_uuid.uuid4(),
            email="super@optics.demo",
            hashed_password=hash_password("demo"),
            role=UserRole.super_admin.value,
            tenant_id=None,
            supervisor_visibility=SupervisorVisibility.show.value,
        )
        db.add(u)
        await db.commit()
        return HTMLResponse(content=f"created: id={u.id}", media_type="text/plain")


@router.get("/_/logout", response_class=HTMLResponse)
async def demo_logout_helper(next: str = "/login"):
    """Phase 6 screenshot helper: clears localStorage atlas_token and
    redirects to ?next= (default /login). Used to capture anonymous
    login screen without manual cache clearing."""
    if not next.startswith("/") or next.startswith("//"):
        next = "/login"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Logout…</title></head>
<body><script>
localStorage.removeItem('atlas_token');
localStorage.removeItem('atlas_email');
location.replace({next!r});
</script></body></html>"""
    return HTMLResponse(content=html)


@router.get("/_/demo-login", response_class=HTMLResponse)
async def demo_login_helper(email: str, next: str = "/"):
    """Phase 6 screenshot helper: instant-login for *.demo accounts.

    Returns a tiny HTML page that POSTs /auth/login with hard-coded
    'demo' password, saves the resulting token to localStorage, and
    redirects to ?next=<path>.

    Strict guard: ONLY emails on demo tenants are accepted (currently
    `@optics.demo` and `@semicon.demo`). Any other email returns 404
    (not 403, to avoid hint of route existence).

    Disabled in production: settings.app_env == 'production' returns 404.
    """
    if getattr(settings, "app_env", "development") == "production":
        raise HTTPException(status_code=404)
    DEMO_DOMAINS = ("@optics.demo", "@semicon.demo")
    if not any(email.endswith(d) for d in DEMO_DOMAINS):
        raise HTTPException(status_code=404)
    # Validate next is same-origin path (no open redirect).
    if not next.startswith("/") or next.startswith("//"):
        next = "/"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Demo login…</title></head><body>
<p style="font-family: sans-serif; padding: 40px;">Setting up demo session for <b>{email}</b>…</p>
<script>
(async function() {{
  try {{
    const r = await fetch('/auth/login', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email: {email!r}, password: 'demo'}}),
    }});
    if (!r.ok) {{
      document.body.innerHTML = '<p style="color:red">Login failed: HTTP ' + r.status + '</p>';
      return;
    }}
    const d = await r.json();
    localStorage.setItem('atlas_token', d.access_token);
    localStorage.setItem('atlas_email', {email!r});
    location.replace({next!r});
  }} catch (e) {{
    document.body.innerHTML = '<p style="color:red">Error: ' + e.message + '</p>';
  }}
}})();
</script></body></html>"""
    return HTMLResponse(content=html)
