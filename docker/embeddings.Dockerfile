FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn sentence-transformers

COPY docker/embeddings_service.py .

# Non-root user (UID 10002 — не пересекается с atlas:10001 из app.Dockerfile,
# чтобы при общем volume-mount права не конфликтовали).
RUN groupadd -r -g 10002 emb \
    && useradd -r -u 10002 -g emb -d /app -s /sbin/nologin emb \
    && mkdir -p /home/emb/.cache/huggingface \
    && chown -R emb:emb /app /home/emb
ENV HOME=/home/emb
USER emb

# Healthcheck: модель загружается при старте, поэтому start-period длинный.
# /health должен быть в embeddings_service.py — если его нет, healthcheck
# просто будет падать, что пометит контейнер unhealthy и docker compose
# не запустит зависящий app.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=3).status==200 else 1)" || exit 1

CMD ["uvicorn", "embeddings_service:app", "--host", "0.0.0.0", "--port", "8001"]
