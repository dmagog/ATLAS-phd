FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e ".[dev]"

COPY alembic.ini .
COPY alembic/ alembic/

CMD ["uvicorn", "atlas.api.main:app", "--host", "0.0.0.0", "--port", "8731"]
