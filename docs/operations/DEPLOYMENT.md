# CodeGuard — Production Deployment Guide

This guide establishes the deterministic procedures for deploying CodeGuard across Staging and Production environments.

---

## 1. Prerequisites & System Requirements

### Host Minimum Specifications
- **CPU**: 4 Cores (x86_64 or ARM64)
- **Memory**: 8 GB RAM minimum (16 GB recommended for high PR throughput)
- **Disk**: 50 GB NVMe SSD for application logs, container images, and database storage
- **Operating System**: Linux (Ubuntu 22.04 LTS / Debian 12 / RHEL 9) or Container Engine with Linux virtualization

### Software Dependencies
- **Docker Engine**: 24.0+ with Docker Compose v2.20+
- **Python**: 3.12+ (for operational CLI scripts and migrations)
- **PostgreSQL Client**: `psql` and `pg_isready` (version 16)
- **OpenSSL**: For certificate verification and secret generation

---

## 2. Container Topology & Non-Root Execution

All CodeGuard containers run as unprivileged, non-root system users to eliminate container escape vectors:

| Container | Image / Base | UID / GID | User / Group | Mount Type | Writable Directories |
|---|---|---|---|---|---|
| `codeguard-api-prod` | `python:3.12-slim` | 1000:1000 | `codeguard:codeguard` | Read-only app mount | `/tmp` (ephemeral) |
| `codeguard-worker-prod`| `python:3.12-slim` | 1000:1000 | `codeguard:codeguard` | Read-only app mount | `/tmp` (ephemeral) |
| `codeguard-web-prod` | `node:22-alpine` | 1001:1001 | `nextjs:nodejs` | Standalone bundle | `/app/.next/cache` |
| `codeguard-postgres-prod`| `postgres:16-alpine` | 70:70 | `postgres:postgres` | Named volume | `/var/lib/postgresql/data` |
| `codeguard-redis-prod` | `redis:7-alpine` | 999:999 | `redis:redis` | Named volume | `/data` |

---

## 3. Production Deployment Procedure

### Step 1: Clone Repository from Clean Release Tag
```bash
git clone https://github.com/your-org/codeguard-ai.git /opt/codeguard-ai
cd /opt/codeguard-ai
git checkout tags/v1.0.0-release
```

### Step 2: Configure Production Environment Variables
Copy the production template and populate with cryptographically generated secrets:
```bash
cp .env.production.example .env.production
chmod 600 .env.production
```
Configure all required variables (see `CONFIGURATION.md` and `SECRETS.md`).

### Step 3: Pre-Deployment Configuration Validation
Run the fail-fast configuration validator:
```bash
python -c "
from app.core.config import Settings
s = Settings(_env_file='.env.production')
print(f'Configuration valid: env={s.APP_ENV}, version={s.APP_VERSION}')
"
```
*If any required production secret is missing, this command exits with a non-zero code and describes the missing variable.*

### Step 4: Build Production Images
Build immutable multi-stage production images:
```bash
docker compose -f docker-compose.prod.yml build --no-cache
```

### Step 5: Start Infrastructure & Run Database Migrations
Start PostgreSQL, Redis, and run Alembic migrations to HEAD:
```bash
# Start backing stores
docker compose -f docker-compose.prod.yml up -d postgres redis
docker compose -f docker-compose.prod.yml ps

# Wait for PostgreSQL healthcheck
until docker compose -f docker-compose.prod.yml exec postgres pg_isready -U "$POSTGRES_USER"; do
    echo "Waiting for PostgreSQL..."
    sleep 2
done

# Run Alembic migrations to HEAD
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

### Step 6: Launch Application Services
Launch API, Worker, and Web Dashboard:
```bash
docker compose -f docker-compose.prod.yml up -d api worker web
```

### Step 7: Verify Service Health & Readiness
Execute health probes against all running services:
```bash
# 1. API Liveness & Readiness
curl -sSf http://localhost:8000/api/v1/live | jq .
curl -sSf http://localhost:8000/api/v1/ready | jq .

# 2. Web Dashboard
curl -sSf -I http://localhost:3000/ | grep "HTTP/1.1 200 OK"
```

---

## 4. Reverse Proxy & TLS Configuration

In production, an external reverse proxy (NGINX, Caddy, or Cloud Load Balancer) terminates TLS and enforces security headers:

```nginx
# Sample NGINX Production VirtualHost
server {
    listen 443 ssl http2;
    server_name api.codeguard.ai;

    ssl_certificate /etc/letsencrypt/live/api.codeguard.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.codeguard.ai/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # OWASP Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # GitHub Webhook Endpoint
    location /api/v1/webhooks/github {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 10M;
    }

    # API Endpoints
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 25M;
    }
}
```

---

## 5. Graceful Shutdown & Drain

When updating or restarting services:
```bash
# Gracefully stop worker (waits for active Celery tasks to finish within 30s)
docker compose -f docker-compose.prod.yml stop -t 30 worker

# Gracefully stop web & api
docker compose -f docker-compose.prod.yml stop -t 15 web api

# Shutdown remaining backing infrastructure
docker compose -f docker-compose.prod.yml down
```

---

## 6. Host Infrastructure Status (Rule 94 Audit)

- **Local Windows Workspace**:
  - Python 3.13 / Virtual Environment `.venv` : Active and verified.
  - Next.js Web Build : Compiled and verified (`npm run build`).
  - Docker CLI (v29.5.3) : Installed.
  - Docker Engine Daemon : `NOT RUNNING` on host local pipe (`//./pipe/dockerDesktopLinuxEngine`).
- **Operational Classification**:
  - Code, migrations, security gates, acceptance tests, build artifacts, and fail-fast configurations: **VERIFIED PASS**.
  - Live container cluster orchestration in production cloud: **NOT TESTED — DEPENDENCY UNAVAILABLE (Local Docker daemon offline; Remote cloud cluster not configured)**.
