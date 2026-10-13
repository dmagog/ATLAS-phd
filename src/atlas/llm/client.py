"""
LLM client for OpenRouter or GigaChat (settings.llm_provider).
Both speak the OpenAI chat completions format.
Retries on 429 and 5xx with exponential backoff (max 2 retries).

GigaChat specifics: access_token via OAuth (Basic auth key → ~30 min token,
cached per process and refreshed on 401), TLS signed by the Russian Trusted
Root CA (bundle in atlas/resources/certs).
"""
import time
import uuid
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from atlas.core.config import settings
from atlas.core.logging import logger

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_GIGACHAT_CA_BUNDLE = Path(__file__).resolve().parents[1] / "resources" / "certs" / "russian_trusted_ca.pem"
# Перевыпускаем токен за минуту до истечения, чтобы не поймать 401 в полёте.
_TOKEN_REFRESH_MARGIN_MS = 60_000


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
        timeout = httpx.Timeout(timeout=settings.request_timeout_ms / 1000, connect=5.0)
        self._gigachat = settings.llm_provider == "gigachat"
        if self._gigachat:
            self._url = f"{settings.gigachat_base_url.rstrip('/')}/chat/completions"
            self._default_model = settings.gigachat_model
            self._client = httpx.AsyncClient(timeout=timeout, verify=str(_GIGACHAT_CA_BUNDLE))
        else:
            self._url = _OPENROUTER_URL
            self._default_model = settings.llm_model_id
            self._client = httpx.AsyncClient(
                timeout=timeout,
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "HTTP-Referer": "https://github.com/atlas-phd",
                    "X-Title": "ATLAS phd",
                },
            )
        self._token: str | None = None
        self._token_expires_at_ms = 0

    async def close(self) -> None:
        await self._client.aclose()

    async def _gigachat_token(self) -> str:
        now_ms = int(time.time() * 1000)
        if self._token and now_ms < self._token_expires_at_ms - _TOKEN_REFRESH_MARGIN_MS:
            return self._token
        resp = await self._client.post(
            settings.gigachat_oauth_url,
            headers={
                "Authorization": f"Basic {settings.gigachat_auth_key}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"scope": settings.gigachat_scope},
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        # expires_at — миллисекунды эпохи; без него считаем токен живым 30 минут.
        self._token_expires_at_ms = int(payload.get("expires_at") or now_ms + 30 * 60 * 1000)
        return self._token

    async def _post(self, payload: dict) -> httpx.Response:
        if not self._gigachat:
            return await self._client.post(self._url, json=payload)
        token = await self._gigachat_token()
        resp = await self._client.post(
            self._url, json=payload, headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code == 401:
            # Токен отозван раньше expires_at — перевыпускаем один раз.
            self._token = None
            token = await self._gigachat_token()
            resp = await self._client.post(
                self._url, json=payload, headers={"Authorization": f"Bearer {token}"}
            )
        return resp

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
        model = model or self._default_model
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        logger.info("llm_request", model=model, messages_count=len(messages), request_id=request_id)

        resp = await self._post(payload)
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
