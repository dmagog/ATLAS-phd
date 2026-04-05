"""
LLM client for OpenRouter API.
Compatible with OpenAI chat completions format.
Retries on 429 and 5xx with exponential backoff (max 2 retries).
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from atlas.core.config import settings
from atlas.core.logging import logger

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exc, httpx.TimeoutException):
        return True
    return False


class LLMClient:
    def __init__(self) -> None:
        timeout_s = settings.request_timeout_ms / 1000
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=timeout_s, connect=5.0),
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "HTTP-Referer": "https://github.com/atlas-phd",
                "X-Title": "ATLAS phd",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception(_should_retry),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_id: str = "",
    ) -> str:
        model = model or settings.llm_model_id
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        logger.info("llm_request", model=model, messages_count=len(messages), request_id=request_id)

        resp = await self._client.post(_OPENROUTER_URL, json=payload)
        resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        logger.info(
            "llm_response",
            model=model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            request_id=request_id,
        )
        return content


# Module-level singleton — initialised once, reused across requests
llm_client = LLMClient()
