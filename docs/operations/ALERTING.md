# CodeGuard — Alerting Policies & Operational Thresholds

This document defines the alerting thresholds, severity matrix, trigger conditions, and escalation paths for CodeGuard.

---

## 1. Incident Severity Classification

| Severity Level | Definition | Response SLA | Target Channels |
|---|---|---|---|
| **P1 — CRITICAL** | Total service outage, database inaccessible, data corruption, or security policy bypass. | < 15 minutes (24/7) | PagerDuty, SMS, Critical Slack (#ops-alerts-p1) |
| **P2 — HIGH** | Review queue backlog accumulating, high Gemini failure rate, degraded database pool, or webhook drops. | < 30 minutes (24/7) | PagerDuty, Slack (#ops-alerts-p2) |
| **P3 — MEDIUM** | Non-critical background task failure, transient external API throttling, or single worker node degradation. | < 2 business hours | Slack (#ops-alerts-p3), Email |
| **P4 — LOW** | Informational warnings, planned maintenance notifications, or individual model cost threshold queries. | Next business day | Slack (#ops-notifications) |

---

## 2. Production Alert Definitions

### Alert: `API_SERVICE_UNAVAILABLE`
- **Severity**: P1 — CRITICAL
- **Trigger**: `/api/v1/live` returns non-200 or times out for 3 consecutive checks (30 seconds).
- **Impact**: External GitHub webhooks and dashboard users cannot reach CodeGuard.
- **Remediation**:
  1. Inspect container status: `docker ps -f name=codeguard-api`.
  2. Check last 100 log lines: `docker logs --tail 100 codeguard-api`.
  3. Restart API container: `docker compose -f docker-compose.prod.yml restart api`.

### Alert: `READINESS_DEGRADED_DB_OR_REDIS`
- **Severity**: P1 — CRITICAL
- **Trigger**: `/api/v1/ready` returns HTTP 503 for > 30 seconds.
- **Impact**: API cannot write review jobs or authenticate users; queue broker disconnected.
- **Remediation**:
  1. Check response JSON to identify culprit: `curl http://localhost:8000/api/v1/ready`.
  2. If `postgres="disconnected"`, inspect PostgreSQL container health and connection pool limits (`DB_POOL_SIZE`).
  3. If `redis="disconnected"`, inspect Redis process and memory usage.

### Alert: `WORKER_QUEUE_BACKLOG_HIGH`
- **Severity**: P2 — HIGH
- **Trigger**: Celery queue length in Redis exceeds 50 pending jobs for > 5 minutes:
  ```bash
  redis-cli -a "$REDIS_PASSWORD" llen celery > 50
  ```
- **Impact**: Pull request reviews delayed; PR turnaround time degrades.
- **Remediation**:
  1. Check worker logs for hung tasks: `docker logs --tail 200 codeguard-worker`.
  2. Scale worker concurrency:
     ```bash
     docker compose -f docker-compose.prod.yml up -d --scale worker=4
     ```

### Alert: `GEMINI_REPEATED_FAILURES`
- **Severity**: P2 — HIGH
- **Trigger**: More than 5% of Gemini API calls return 5xx or 429 over a 5-minute rolling window.
- **Impact**: Multi-agent review pipeline delays; reviews fall back to retries.
- **Remediation**:
  1. Check Google AI Studio status dashboard for upstream provider degradation.
  2. Confirm account quota and rate limits.
  3. If transient, verify exponential backoff is active (`AGENT_MAX_RETRIES=2`).

### Alert: `GITHUB_PUBLICATION_FAILURES`
- **Severity**: P2 — HIGH
- **Trigger**: GitHub review publication API failure rate > 5% over 10 minutes.
- **Impact**: Approved reviews fail to post comments to GitHub pull requests.
- **Remediation**:
  1. Inspect `github_review_publications` table for error payloads.
  2. Check GitHub status at https://www.githubstatus.com.
  3. Verify GitHub App installation token has not expired or lost repository permissions.

### Alert: `POLICY_DENIAL_SPIKE`
- **Severity**: P2 — HIGH
- **Trigger**: More than 10 policy action authorization denials in 5 minutes.
- **Impact**: Possible credential tampering, unauthorized agent escalation, or misconfigured token.
- **Remediation**:
  1. Query `tool_execution_audits` for `authorization_decision='DENY'`.
  2. Inspect caller `principal_id` and attempted `tool_name`.
  3. If suspicious, follow `INCIDENT_RESPONSE.md` for credential rotation.

---

## 3. Alert Silencing & Maintenance Windows

To suppress alerts during scheduled maintenance:
1. Schedule a silence window in the monitoring platform with the ticket reference (`MAINT-1234`).
2. Do NOT disable alerting permanently or remove health probes.
3. Post maintenance, verify that all probes return `200 OK` and clear the silence window.
