"""Простейший in-memory rate-limiter для защиты login от brute-force.

Хранит счётчики попыток в памяти процесса. Этого достаточно для одного
uvicorn-воркера (наш текущий деплой). При горизонтальном масштабировании
на несколько процессов/инстансов нужно заменить на Redis-based limiter
(slowapi+redis или fastapi-limiter) — каждый процесс будет считать сам
по себе, и злоумышленник сможет проходить N*workers попыток.

API: единая функция `check_login_attempt(ip, identifier)` — поднимает
HTTPException(429) если лимит превышен, иначе фиксирует попытку.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status

_WINDOW_SEC = 300

# Два уровня лимита, чтобы покрыть разные сценарии атак:
#   (IP, email) — словарный перебор пароля одного аккаунта.
#   (IP)        — перебор разных аккаунтов с одного хоста (включая
#                 спрей-атаку «один пароль на сотню email-адресов»).
# Числа умеренные: легитимный пользователь редко превышает 5 ошибок,
# но 50 попыток с одного IP за 5 минут — уже подозрительно.
_MAX_PER_IP_EMAIL = 5
_MAX_PER_IP = 50

_per_ip_email: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_per_ip: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _client_ip(request) -> str:
    """Best-effort извлечение IP. За reverse-proxy нужно настроить
    proxy-headers в uvicorn (--forwarded-allow-ips) и брать X-Forwarded-For;
    без proxy `request.client.host` достаточно."""
    if request is None or request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def _trim_and_check(bucket: deque[float], now: float, cutoff: float, limit: int) -> int | None:
    """Сдвинуть окно и вернуть retry_after если лимит исчерпан, иначе None."""
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return int(_WINDOW_SEC - (now - bucket[0])) + 1
    return None


def check_login_attempt(request, identifier: str) -> None:
    """Проверить оба лимита и зафиксировать попытку.

    `identifier` — нормализованный email (lower-cased), чтобы попытки
    'Admin@x.y' и 'admin@x.y' считались вместе.

    Поднимает HTTPException(429, Retry-After) при превышении любого из
    лимитов. Вызывать ДО проверки пароля.
    """
    ip = _client_ip(request)
    email_key = (ip, identifier.strip().lower())
    now = time.monotonic()
    cutoff = now - _WINDOW_SEC

    with _lock:
        retry_a = _trim_and_check(_per_ip_email[email_key], now, cutoff, _MAX_PER_IP_EMAIL)
        retry_b = _trim_and_check(_per_ip[ip], now, cutoff, _MAX_PER_IP)
        retry_after = retry_a or retry_b
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много попыток входа. Попробуйте позже.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )
        _per_ip_email[email_key].append(now)
        _per_ip[ip].append(now)


def reset_login_attempts(request, identifier: str) -> None:
    """Сбросить счётчик (IP, email) при успешном логине. Глобальный
    per-IP счётчик НЕ сбрасываем — иначе атакующий, имеющий валидный
    аккаунт, обнулял бы себе перебор остальных."""
    ip = _client_ip(request)
    key = (ip, identifier.strip().lower())
    with _lock:
        _per_ip_email.pop(key, None)


# ── LLM-квоты на пользователя ────────────────────────────────────────────────
# Каждый /qa/message, /chat/message, /self-check/* запрос дёргает OpenRouter.
# Без лимита один залогиненный студент может в цикле выжать бюджет ключа.
# Лимит по умолчанию: 60 запросов в час на пользователя — ограничивает злодея
# и комфортно для легитимной работы. super-admin исключён (тестовые скрипты).
_LLM_WINDOW_SEC = 3600
_LLM_MAX_PER_USER = 60

_llm_per_user: dict[str, deque[float]] = defaultdict(deque)


def check_llm_quota(user_id: str) -> None:
    """Проверить и зафиксировать квоту LLM-вызовов для пользователя.

    Вызывать в FastAPI Dependency для всех эндпоинтов, которые в цепочке
    делают вызов LLM (qa, chat, self-check). При превышении лимита
    поднимается HTTPException(429, Retry-After).

    Если в будущем хочется per-tenant квоту вдобавок — добавить второй
    счётчик (по аналогии с login).
    """
    now = time.monotonic()
    cutoff = now - _LLM_WINDOW_SEC
    with _lock:
        bucket = _llm_per_user[user_id]
        retry_after = _trim_and_check(bucket, now, cutoff, _LLM_MAX_PER_USER)
        if retry_after is not None:
            # Здесь окно час — отдаём оставшееся время, не _WINDOW_SEC
            real_retry = int(_LLM_WINDOW_SEC - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Превышена квота LLM-запросов "
                    f"({_LLM_MAX_PER_USER}/час). Попробуйте позже."
                ),
                headers={"Retry-After": str(max(real_retry, 1))},
            )
        bucket.append(now)
