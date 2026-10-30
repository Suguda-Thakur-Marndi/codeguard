# CodeGuard — Master Production Operations Runbook

**Document ID**: `DOC-OPS-RUNBOOK-01`  
**Application Version**: `1.0.0`  
**Target Operations**: SRE, DevOps, and On-Call Engineers  
**Classification**: Operational Canonical Runbook  
**Last Verified**: 2026-09-29  

---

## 1. Quick Reference: Service Topology & Key Ports

| Service Component | Port | Health / Liveness Probe | Log Event Signature | Verification Status |
| :--- | :---: | :--- | :--- | :---: |
| **API Server (FastAPI)** | `8000` | `GET /api/v1/live`, `GET /api/v1/ready` | `event="http_request_completed"` | **VERIFIED** |
| **Review Worker (Celery)** | — | Celery ping / Redis heartbeat | `event="review_job_started"` | **VERIFIED** |
| **Frontend Dashboard** | `3000` | `GET /` (HTTP 200) | Next.js server access logs | **VERIFIED** |
| **PostgreSQL Database** | `5432` | `pg_isready -U codeguard` | PostgreSQL transaction logs | **VERIFIED** |
| **Redis Broker & Cache** | `6379` | `redis-cli ping` $\rightarrow$ `PONG` | Redis persistence logs | **VERIFIED** |

---

## 2. Standard Service Lifecycle Procedures

### 2.1 Starting Services

#### Production Stack (Docker Compose):
```bash
# Start all containerized services in background
docker compose -f docker-compose.prod.yml up -d --build

# Verify all containers are healthy
docker compose -f docker-compose.prod.yml ps
```
*Status*: **VERIFIED IN CI / CONTAINER WORKFLOWS**.

#### Local Developer Stack (Manual Processes):
```bash
# 1. Start API (Terminal 1)
.\.venv\Scripts\uvicorn app.main:app --app-dir apps/api --port 8000

# 2. Start Celery Worker (Terminal 2, Windows solo pool)
.\.venv\Scripts\celery -A app.workers.celery_app worker --pool=solo -l info

# 3. Start Next.js Web (Terminal 3)
cd apps/web && npm run dev
```
*Status*: **VERIFIED ON LOCAL HOST**.

### 2.2 Stopping Services
```bash
# Gracefully stop production stack
docker compose -f docker-compose.prod.yml down

# Stop with volume data retention
docker compose -f docker-compose.prod.yml stop
```

---

## 3. Health & Observability Inspection

### 3.1 Probing Health Endpoints
```bash
# 1. Process Liveness Check (Should return 200 OK immediately)
curl -i http://localhost:8000/api/v1/live

# 2. Dependency Readiness Check (Validates DB pool and Redis connectivity)
curl -i http://localhost:8000/api/v1/ready
```

### 3.2 Inspecting Structured Logs & Traces
All application logs are formatted as single-line structured JSON with causally correlated `request_id` and `trace_id`.

```bash
# View live API logs filtered for warnings and errors
docker logs -f codeguard-api | grep -E '"level": "(WARNING|ERROR|CRITICAL)"'

# Trace a specific review job lifecycle using its UUID
docker logs codeguard-worker | grep "3fa85f64-5717-4562-b3fc-2c963f66afa6"

# Verify that sensitive tokens are redacted (should yield zero results)
docker logs codeguard-api | grep -E "ghp_[A-Za-z0-9]{36}|AIzaSy[A-Za-z0-9_-]{33}"
```

---

## 4. Diagnosing Incidents & Operational Failures

### 4.1 Diagnosing Failed Review Jobs
1. **Identify Job Failure**:
   ```sql
   SELECT id, repository_id, status, error_message, updated_at 
   FROM review_jobs 
   WHERE status = 'FAILED' 
   ORDER BY updated_at DESC LIMIT 10;
   ```
2. **Inspect Detailed Agent Traces**:
   ```sql
   SELECT agent_name, execution_status, error_message, duration_ms 
   FROM agent_runs 
   WHERE review_job_id = '<job-uuid>';
   ```
3. **Common Root Causes**:
   - `DiffTooLargeError`: Diff exceeds 10,000 lines; system conservatively aborted to protect memory.
   - `RateLimitError`: Upstream Gemini or GitHub API exhausted quota.
   - `SyntaxParseError`: Unsupported novel language grammar in modified file.

---

### 4.2 Diagnosing Queue Backlog (Redis / Celery)
1. **Check Celery Backlog in Redis**:
   ```bash
   docker exec -it codeguard-redis redis-cli llen celery
   ```
   *Interpretation*: If length $> 50$, workers are falling behind ingress webhooks.
2. **Inspect Active Worker Processes**:
   ```bash
   docker exec -it codeguard-worker celery -A app.workers.celery_app inspect active
   ```
3. **Remediation**: Scale worker replicas:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --scale worker=4
   ```

---

### 4.3 Handling Gemini API Outages or Rate Limits
1. **Symptom**: Logs show `429 ResourceExhausted` or `503 ServiceUnavailable` from `google-genai`.
2. **Automated Handling**: System retries with exponential backoff (2s, 4s, 8s, up to 30s).
3. **Emergency Circuit Breaker**:
   - Temporarily pause automatic review job dispatch:
     Set `CELERY_TASK_ALWAYS_EAGER=false` and stop workers to let webhooks queue in Redis.
   - Switch model tier to fast model if pro model is throttled:
     Update `GEMINI_MODEL_REASONING=gemini-2.5-flash` in container environment and restart workers.

---

### 4.4 Disabling Review Publication (Emergency Kill-Switch)
If CodeGuard produces erroneous comments or encounters an active regression:

1. **Option A: Organization Policy Kill-Switch (No restart required)**:
   Make API call to update organization policy:
   ```bash
   curl -X PUT http://localhost:8000/api/v1/policies \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -H "Content-Type: application/json" \
     -d '{"require_human_approval_all": true, "auto_publish_enabled": false}'
   ```
   *Result*: 100% of reviews are quarantined in `PENDING_APPROVAL` state; zero comments publish to GitHub.
2. **Option B: Webhook Ingress Shutdown**:
   Revoke or invalidate `GITHUB_WEBHOOK_SECRET` in environment, causing all incoming webhooks to fail HMAC verification with HTTP 401.

---

## 5. Security & Credential Rotation Procedures

### 5.1 Rotating Secret Key (`SECRET_KEY`)
1. Generate new 32-byte hexadecimal secret:
   ```bash
   openssl rand -hex 32
   ```
2. Update `SECRET_KEY` in environment vault / `.env`.
3. Restart `api` service.
   *Impact*: Existing user JWT sessions are invalidated; operators must re-login.

### 5.2 Rotating GitHub Webhook Secret (`GITHUB_WEBHOOK_SECRET`)
1. Generate new secret: `openssl rand -hex 32`.
2. In GitHub Organization $\rightarrow$ GitHub App $\rightarrow$ Settings $\rightarrow$ Webhook Secret: Update secret.
3. Update `GITHUB_WEBHOOK_SECRET` in CodeGuard API environment and reload service.

### 5.3 Rotating GitHub App Private Key (`GITHUB_PRIVATE_KEY`)
1. In GitHub App Settings $\rightarrow$ Generate a new private key (`.pem`).
2. Update base64/PEM private key in environment secrets manager.
3. Restart `api` and `worker` services.
4. Verify connection by triggering test webhook.
5. In GitHub App Settings $\rightarrow$ Delete old private key.

---

## 6. Database Maintenance & Disaster Recovery

### 6.1 Executing Automated Backup
```bash
python scripts/backup_db.py --output-dir ./backups
```
- Creates gzip-compressed snapshot.
- Emits SHA-256 integrity checksum file (`<snapshot>.sha256`).
- Cleans up backups older than 30 days.

### 6.2 Executing Verified Restoration Drill
```bash
python scripts/restore_db.py --backup-file ./backups/codeguard_backup_latest.sql.gz --confirm-restore
```
- Validates SHA-256 checksum before restoration.
- Drops and recreates target schema.
- Restores all 27 tables.
- Asserts that table count $\ge 27$ upon completion.
*Status*: **VERIFIED IN ACCEPTANCE SUITE (AUDIT-BK)**.

---

## 7. Rollback Procedures

### 7.1 Application Code Rollback
```bash
# 1. Checkout previous stable release tag
git checkout v1.0.0-stable

# 2. Rebuild and restart containers
docker compose -f docker-compose.prod.yml up -d --build
```

### 7.2 Database Schema Rollback
```bash
# Roll back single Alembic migration revision
alembic -c apps/api/alembic.ini downgrade -1

# Verify applied revision matches expected previous state
alembic -c apps/api/alembic.ini current
```
