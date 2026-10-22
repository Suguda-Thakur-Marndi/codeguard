# Production Dockerfile for CodeGuard AI API and Worker
FROM python:3.12-slim AS runner

WORKDIR /app

# System runtime dependencies & security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpq5 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root system user and group
RUN groupadd -g 1000 codeguard && \
    useradd -u 1000 -g codeguard -m -s /bin/bash codeguard

# Install packages into system python
COPY packages/code-intelligence ./packages/code-intelligence
COPY apps/api/pyproject.toml apps/api/README.md ./apps/api/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ./packages/code-intelligence && \
    pip install --no-cache-dir ./apps/api

WORKDIR /app/apps/api
COPY apps/api/app/ ./app/
COPY apps/api/alembic/ ./alembic/
COPY apps/api/alembic.ini ./

RUN chown -R codeguard:codeguard /app

USER codeguard

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
