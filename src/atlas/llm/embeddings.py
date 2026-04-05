"""
Client for the local embeddings sidecar service.
"""
import httpx
from atlas.core.config import settings
from atlas.core.logging import logger


async def get_embeddings(texts: list[str], request_id: str = "") -> list[list[float]]:
    """Embed a batch of texts. Returns list of float vectors."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.embeddings_url}/embed",
            json={"texts": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "embeddings_fetched",
            count=len(texts),
            model=data.get("model"),
            request_id=request_id,
        )
        return data["embeddings"]


async def get_embedding(text: str, request_id: str = "") -> list[float]:
    """Embed a single text."""
    results = await get_embeddings([text], request_id=request_id)
    return results[0]
