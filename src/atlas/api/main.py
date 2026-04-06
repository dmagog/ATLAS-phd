from contextlib import asynccontextmanager
from fastapi import FastAPI
from atlas.core.logging import configure_logging
from atlas.db.session import AsyncSessionLocal
from atlas.api.startup import seed_admin, reset_stale_jobs
from atlas.api.routers import auth, admin, qa, selfcheck, web, chat
from atlas.llm.client import llm_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    async with AsyncSessionLocal() as db:
        await seed_admin(db)
        await reset_stale_jobs(db)
    yield
    await llm_client.close()


app = FastAPI(title="ATLAS phd", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(qa.router)
app.include_router(selfcheck.router)
app.include_router(chat.router)
app.include_router(web.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
