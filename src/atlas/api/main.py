from contextlib import asynccontextmanager
from fastapi import FastAPI
from atlas.core.logging import configure_logging
from atlas.db.session import AsyncSessionLocal
from atlas.api.startup import seed_admin
from atlas.api.routers import auth, admin
from atlas.llm.client import llm_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    async with AsyncSessionLocal() as db:
        await seed_admin(db)
    yield
    await llm_client.close()


app = FastAPI(title="ATLAS phd", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
