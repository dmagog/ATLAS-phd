FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn sentence-transformers

COPY docker/embeddings_service.py .

CMD ["uvicorn", "embeddings_service:app", "--host", "0.0.0.0", "--port", "8001"]
