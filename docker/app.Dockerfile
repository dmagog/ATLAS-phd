# Multi-stage build:
#   - dev: hot-reload, dev-deps (pytest/ruff), auto-migrate в CMD.
#         Используется в docker-compose `build.target=dev` (default).
#   - production: без --reload, без dev-deps, БЕЗ auto-migrate в CMD
#         (миграции делает scripts/deploy.sh отдельным one-shot контейнером
#         ДО старта app — см. roadmap §M6.A). Запускается под non-root user'ом.
#         Используется в .github/workflows/build-image.yml (target=production).

# ─── Stage 1: общая база ──────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# Системные зависимости для argon2-cffi и pypdf — нужны и dev'у, и prod'у.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY alembic.ini .
COPY alembic/ alembic/

# ─── Stage 2: dev (default) ───────────────────────────────────────────────
FROM base AS dev

# Editable install c [dev] extras для hot-reload и тестов.
RUN pip install --no-cache-dir -e ".[dev]"

# Auto-migrate в CMD удобен для dev (новая миграция → вверх на старте).
# Для prod — НЕ годится: упавшая миграция не должна блокировать рестарт.
CMD ["sh", "-c", "alembic upgrade head && uvicorn atlas.api.main:app --host 0.0.0.0 --port 8731 --reload --reload-dir /app/src"]

# ─── Stage 3: production ──────────────────────────────────────────────────
FROM base AS production

# Non-editable install только runtime-зависимостей (без [dev]).
RUN pip install --no-cache-dir .

# Non-root user. UID 10001 — вне диапазона system-users, не конфликтует с
# host'ом при volume-mount'ах.
RUN groupadd -r -g 10001 atlas \
    && useradd -r -u 10001 -g atlas -d /app -s /sbin/nologin atlas \
    && chown -R atlas:atlas /app
USER atlas

# Healthcheck (docker compose может им пользоваться).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8731/health',timeout=3).status==200 else 1)" || exit 1

# Без --reload, без alembic upgrade head — миграции прогоняются отдельным
# `docker compose run --rm app alembic upgrade head` ДО старта (см. deploy.sh).
CMD ["uvicorn", "atlas.api.main:app", "--host", "0.0.0.0", "--port", "8731"]
