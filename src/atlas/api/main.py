from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from atlas.core.logging import configure_logging
from atlas.db.session import AsyncSessionLocal
from atlas.api.startup import seed_admin, reset_stale_jobs
from atlas.api.routers import auth, admin, qa, selfcheck, web, chat, invites, tenants
from atlas.llm.client import llm_client

_STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    async with AsyncSessionLocal() as db:
        await seed_admin(db)
        await reset_stale_jobs(db)
    yield
    await llm_client.close()


app = FastAPI(title="ATLAS phd", version="0.1.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(qa.router)
app.include_router(selfcheck.router)
app.include_router(chat.router)
app.include_router(invites.router)
app.include_router(tenants.router)
app.include_router(web.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
