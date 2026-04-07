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
        # Standard HTTP error codes worth retrying
        if exc.response.status_code in (429, 500, 502, 503, 504):
            return True
        # OpenRouter wraps upstream rate-limits as 200 + {"error": ...};
        # we re-raise them as HTTPStatusError — catch by message.
        if "rate" in str(exc).lower():
            return True
    # Network-level failures: dropped connection, incomplete read, timeout
    if isinstance(exc, (httpx.TimeoutException,
                        httpx.RemoteProtocolError,
                        httpx.ReadError)):
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
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=5, max=60),
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

        # OpenRouter free-tier can return {"error": {...}} instead of {"choices": [...]}
        if "error" in data:
            err = data["error"]
            code = err.get("code", 0)
            msg = err.get("message", str(err))
            logger.warning("llm_api_error", code=code, message=msg, request_id=request_id)
            # Treat rate-limit errors as retriable
            if code in (429, 503) or "rate" in msg.lower():
                raise httpx.HTTPStatusError(msg, request=resp.request, response=resp)
            raise RuntimeError(f"LLM API error {code}: {msg}")

        if not data.get("choices"):
            logger.error("llm_empty_choices", response_keys=list(data.keys()), request_id=request_id)
            raise RuntimeError(f"LLM returned no choices: {list(data.keys())}")

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
