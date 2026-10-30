# CodeGuard — Health Checks & Readiness Probes

This document details the health, liveness, and readiness probe architecture implemented across CodeGuard services.

---

## 1. Architectural Philosophy: Liveness vs. Readiness

CodeGuard strictly segregates **Liveness** from **Readiness** to prevent cascading failures:

- **Liveness Probes (`/live`)**:
  - Confirms solely that the application process is running and its event loop can respond to HTTP requests.
  - **Does NOT check external dependencies** (PostgreSQL, Redis, Gemini, GitHub).
  - *Action on Failure*: Restart container immediately.

- **Readiness Probes (`/ready`)**:
  - Confirms that the service has established active, healthy connections to its required backing stores (PostgreSQL connection pool, Redis socket).
  - *Action on Failure*: Remove instance from reverse proxy / load balancer traffic routing (returns HTTP 503 Service Unavailable). Does NOT restart the container.

---

## 2. API Server Probes (`codeguard-api` :8000)

### Liveness Probe: `GET /api/v1/live`
- **Protocol**: HTTP/1.1
- **Authentication**: None (Public health endpoint)
- **Response Codes**:
  - `200 OK`: Process alive and responsive.
- **Payload Schema**:
  ```json
  {
    "status": "ok",
    "app": "CodeGuard",
    "version": "1.0.0",
    "environment": "production",
    "git_revision": "v1.0.0-release"
  }
  ```

### Readiness Probe: `GET /api/v1/ready`
- **Protocol**: HTTP/1.1
- **Authentication**: None
- **Dependencies Checked**:
  1. PostgreSQL database connectivity (`SELECT 1` via `check_db_connectivity()`).
  2. Redis ping connectivity (`client.ping()` with 2.0s socket timeout).
- **Response Codes**:
  - `200 OK`: Both PostgreSQL and Redis are connected.
  - `503 SERVICE UNAVAILABLE`: Either PostgreSQL or Redis is disconnected.
- **Healthy Payload (HTTP 200)**:
  ```json
  {
    "status": "ready",
    "postgres": "connected",
    "redis": "connected"
  }
  ```
- **Degraded Payload (HTTP 503)**:
  ```json
  {
    "status": "degraded",
    "postgres": "disconnected",
    "redis": "connected"
  }
  ```

### General Info Probe: `GET /api/v1/health`
- **Protocol**: HTTP/1.1
- **Purpose**: Operational inspection and version discovery.
- **Response Codes**: `200 OK`

---

## 3. Celery Worker Probes (`codeguard-worker`)

The worker does not expose an HTTP socket. Health is monitored via Celery inspect commands against Redis:

```bash
# Verify worker process responsive
docker exec codeguard-worker celery -A app.workers.celery_app inspect ping

# Output on healthy worker:
# -> celery@codeguard-worker: OK
```

---

## 5. PostgreSQL & Redis Probes

### PostgreSQL Probe
```bash
docker exec codeguard-postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
# Output: /var/run/postgresql:5432 - accepting connections
```

### Redis Probe
```bash
docker exec codeguard-redis redis-cli -a "$REDIS_PASSWORD" ping
# Output: PONG
```

---

## 6. Docker Compose Production Healthcheck Configurations

From `docker-compose.prod.yml`:

```yaml
  # PostgreSQL
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB:-codeguard}"]
    interval: 10s
    timeout: 5s
    retries: 5

  # Redis
  healthcheck:
    test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5

  # API
  healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"]
    interval: 15s
    timeout: 5s
    retries: 3
```
