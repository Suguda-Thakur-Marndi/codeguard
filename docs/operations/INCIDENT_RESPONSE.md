# CodeGuard — Incident Response & SRE Runbooks

This document provides definitive, step-by-step incident response playbooks for site reliability engineers (SRE) and on-call operators.

---

## 1. Incident Lifecycle & Protocols

```
  [1. DETECT] Alert fires / Operator detects anomaly
       │
       ▼
  [2. TRIAGE] Determine severity (P1 - P4) & assign Incident Commander
       │
       ▼
[3. CONTAIN] Execute safe containment action (isolate node / revoke token)
       │
       ▼
 [4. REMEDIATE] Execute scenario playbook & restore service
       │
       ▼
  [5. VERIFY] Execute health, readiness, and smoke tests
       │
       ▼
[6. POST-MORTEM] Document timeline, root cause, and preventative actions
```

---

## 2. Standard Incident Playbooks

### INCIDENT-001: Backend API Unavailable (HTTP 502 / 503)
- **Detection**: Alert `API_SERVICE_UNAVAILABLE` fires; `/api/v1/live` probe fails.
- **Triage**: Check container process and memory state:
  ```bash
  docker ps -f name=codeguard-api
  docker logs --tail 200 codeguard-api
  ```
- **Action**:
  1. If container is in restart loop due to uncaught exception during startup, check environment variables.
  2. If process hung, restart container:
     ```bash
     docker compose -f docker-compose.prod.yml restart api
     ```
  3. Verify probe returns HTTP 200: `curl -f http://localhost:8000/api/v1/live`.

---

### INCIDENT-002: Worker Queue Backlog / Review Processing Stall
- **Detection**: Pull requests receive webhooks (HTTP 202), but reviews remain `PROCESSING`; Redis `llen celery` > 50.
- **Triage**:
  ```bash
  docker exec codeguard-redis redis-cli -a "$REDIS_PASSWORD" llen celery
  docker logs --tail 100 codeguard-worker
  ```
- **Action**:
  1. Inspect whether workers are blocked on external network requests (Gemini or GitHub API timeouts).
  2. If worker processes are deadlocked, gracefully restart the worker service:
     ```bash
     docker compose -f docker-compose.prod.yml restart worker
     ```
  3. Under heavy traffic bursts, scale worker concurrency:
     ```bash
     docker compose -f docker-compose.prod.yml up -d --scale worker=4
     ```
  4. Verify queue drains to 0: `docker exec codeguard-redis redis-cli -a "$REDIS_PASSWORD" llen celery`.

---

### INCIDENT-003: Gemini AI Provider Outage / 5xx / 429
- **Detection**: Worker logs show repeated `GoogleAPIError` or HTTP 429/503 from `generativelanguage.googleapis.com`.
- **Triage**:
  1. Check Google AI Studio service status.
  2. Check remaining token quotas on the active API key.
- **Action**:
  1. If quota exhausted, rotate to fallback backup API key per `SECRETS.md`.
  2. If global upstream Google outage, review jobs will automatically retry up to `AGENT_MAX_RETRIES=2` with exponential backoff.
  3. When exhausted, jobs transition to `FAILED` with explicit error logging; reviews do NOT publish corrupt or partial comments.
  4. Once Gemini recovers, re-trigger failed reviews from the Web Dashboard (`/reviews/[jobId] -> Re-run`).

---

### INCIDENT-004: GitHub Webhook or REST API Outage
- **Detection**: Webhook signature failures or GitHub API calls return HTTP 500/502/503.
- **Triage**: Check https://www.githubstatus.com.
- **Action**:
  1. If GitHub is experiencing an outage, pause outbound publication attempts.
  2. Inbound webhook deliveries will be queued by GitHub for up to 24 hours.
  3. For transient 5xx errors during publication, `PublicationService` automatically marks the publication as `FAILED` with retryable flag enabled.
  4. Once GitHub recovers, execute publication retry:
     ```bash
     curl -X POST -H "Authorization: Bearer $ADMIN_JWT" http://localhost:8000/api/v1/publications/$PUB_ID/retry
     ```

---

### INCIDENT-005: Redis Broker Failure
- **Detection**: `/api/v1/ready` returns HTTP 503 (`redis="disconnected"`).
- **Action**:
  1. Check Redis process: `docker logs --tail 50 codeguard-redis`.
  2. Restart Redis container:
     ```bash
     docker compose -f docker-compose.prod.yml restart redis
     ```
  3. Confirm `docker exec codeguard-redis redis-cli -a "$REDIS_PASSWORD" ping` returns `PONG`.
  4. Verify API readiness restores to `ready` (HTTP 200).

---

### INCIDENT-006: PostgreSQL Database Outage
- **Detection**: `/api/v1/ready` returns HTTP 503 (`postgres="disconnected"`).
- **Action**:
  1. Check PostgreSQL process: `docker logs --tail 100 codeguard-postgres`.
  2. Check database connection pool exhaustion:
     ```sql
     SELECT count(*), state FROM pg_stat_activity GROUP BY state;
     ```
  3. If connection pool was exhausted, restart API container to release hung sockets.
  4. If database crashed, restart PostgreSQL container and run `pg_isready`.

---

### INCIDENT-007: Policy Denial Spike or Unauthorized Action Attempt
- **Detection**: `tool_execution_audits` logs spike in `DENY` decisions.
- **Action**:
  1. Inspect `tool_execution_audits` for caller principal IDs and rejected action names.
  2. If unauthorized tampering or repetitive prompt injection is detected, quarantine the review job.
  3. Verify that zero unauthorized GitHub API mutations occurred.

---

### INCIDENT-008: Suspected Credential Leak
- **Detection**: Secret detected in external logs or reported by security audit.
- **Action**:
  1. **Immediate Containment**: Revoke leaked credential in upstream provider (GitHub, Google, or local `SECRET_KEY`).
  2. Generate replacement secret using `openssl rand -hex 32`.
  3. Deploy updated environment to containers.
  4. Query `tool_execution_audits` and API access logs for unauthorized actions taken using the compromised key during the exposure window.

---

### INCIDENT-009: Unauthorized Publication Attempt / Commit Drift
- **Detection**: Zero-Trust Policy Engine blocks publication with reason `Approval is bound to head SHA abc, but current PR head SHA is xyz`.
- **Diagnosis**: Normal, correct security behavior. A developer pushed a new commit to the PR after human approval was granted.
- **Action**:
  1. Notify operator that the PR changed.
  2. Operator or reviewer must inspect the new diff on the dashboard and grant fresh approval for the updated commit SHA.

---

### INCIDENT-010: Database Data Corruption
- **Detection**: Relational constraint failure, missing tables, or query execution failure.
- **Action**: Follow `DISASTER_RECOVERY.md` Scenario 1: Re-provision clean database volume, restore from latest verified backup snapshot using `scripts/restore_db.py --confirm-restore`, and run `alembic upgrade head`.

---

### INCIDENT-011: Adversarial Prompt Injection Escalation
- **Detection**: Audit log detects malicious instruction payload in PR source diff attempting tool escalation.
- **Diagnosis**: Review findings generated by the model contain instructions attempting to invoke unapproved consequential operations.
- **Action**:
  1. The Adversarial Judge and Zero-Trust Policy Engine block unapproved actions by default.
  2. Verify that `FORBIDDEN_OPERATIONS` blocked execution.
  3. Confirm that no GitHub review publication occurred without an authorized human approval record.
