"""Регистрация security-middleware приложения.

Подключает (в порядке wrap'инга — последний зарегистрированный обрабатывается
первым на запрос):
  1. SecurityHeadersMiddleware — заголовки defense-in-depth.
  2. TrustedHostMiddleware — белый список Host (anti host-header injection).
  3. CORSMiddleware — только если задан CORS_ALLOWED_ORIGINS.

Все настройки берутся из atlas.core.config.settings, чтобы поведение
управлялось env-vars без правки кода.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from atlas.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Добавляет defense-in-depth заголовки к каждому ответу.

    HSTS включается только в production (за HTTPS-proxy), иначе браузер
    запиннит dev-домен на https и сломает локальный флоу.

    CSP сделан мягким: разрешаем 'unsafe-inline' для script/style, потому
    что Jinja2-шаблоны (login.html, _app.html, chat.html) содержат inline
    скрипты. Это всё ещё блокирует подгрузку чужих доменов и снижает
    риск XSS через сторонние ресурсы. Жёсткий CSP с nonce'ами — отдельная
    задача, требует переработки шаблонов.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()",
        )
        h.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            ),
        )
        if settings.app_env == "production" and settings.hsts_max_age > 0:
            h.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age}; includeSubDomains",
            )
        return response


def register_security_middleware(app: FastAPI) -> None:
    # CORS — подключаем, только если явно задан список origin'ов.
    # Иначе остаёмся в режиме same-origin (Jinja2 UI ходит на свой же
    # домен — никаких CORS не нужно).
    cors_origins = settings.cors_allowed_origins_list
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Atlas-Tenant"],
            max_age=600,
        )

    # TrustedHost — отбрасываем запросы с неожиданным Host, кроме случая,
    # когда настроено '*' (dev). В production обязательно задать явный список.
    trusted = settings.trusted_hosts_list
    if trusted != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted)

    # Security headers — последним, чтобы заголовки попали в любой ответ,
    # включая 4xx/5xx от других middleware.
    app.add_middleware(SecurityHeadersMiddleware)
