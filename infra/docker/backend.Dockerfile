FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /src
COPY cv-engine ./cv-engine
COPY backend ./backend

WORKDIR /src/backend
RUN uv sync --frozen --no-dev

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /src/backend/.venv /app/.venv
COPY --from=builder /src/backend/app /app/app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
