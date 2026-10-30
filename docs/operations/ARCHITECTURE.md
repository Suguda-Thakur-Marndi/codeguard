# CodeGuard — Production Architecture & System Topology

This document details the production operational architecture, service topologies, process boundaries, network interfaces, and security perimeters implemented in CodeGuard.

---

## 1. System Overview & Component Topology

CodeGuard is structured as a resilient, modular multi-service platform designed to provide automated, adversarial-resistant GitHub Pull Request code reviews under strict human-in-the-loop and zero-trust policy governance.

```
                                  +-----------------------+
                                  |   GitHub Cloud App    |
                                  +-----------+-----------+
                                              |
                   Webhook Events (HMAC-SHA256)|   ^ REST API (Review / Comment)
                                              v   |
+-------------------------------------------------+-----------------------------------+
| CodeGuard Network Perimeter                  |                                   |
|                                                 v                                   |
|                                     +-----------------------+                       |
|                                     |    Reverse Proxy      |                       |
|                                     |      (TLS / 443)      |                       |
|                                     +-----------+-----------+                       |
|                                                 |                                   |
|                     +---------------------------+---------------------------+       |
|                     |                                                       |       |
|                     v (:3000)                                               v (:8000)|
|        +-------------------------+                             +--------------------+
|        |   Frontend Dashboard    |                             |     FastAPI API    |
|        |    (Next.js 15 SSR)     |                             |    Worker Service  |
|        +-------------------------+                             +----------+---------+
|                                                                           |         |
|                     +-----------------------------------------------------+         |
|                     |                                                               |
|                     v                                 v                             |
|         +-----------------------+         +-----------------------+                 |
|         |     Redis 7 Cache     |         |     PostgreSQL 16     |                 |
|         |     & Task Broker     |         |    Relational Store   |                 |
|         |      (Port 6379)      |         |      (Port 5432)      |                 |
|         +-----------+-----------+         +-----------+-----------+                 |
|                     |                                 ^                             |
|                     v                                 |                             |
|         +-----------------------+                     |                             |
|         |     Celery Worker     +---------------------+                             |
|         | (Multi-Agent Pipeline)|                                                   |
|         +-----------+-----------+                                                   |
|                     |                                                               |
+---------------------|---------------------------------------------------------------+
                      |
                      v Outbound HTTPS
          +-----------------------+
          |   Google Gemini API   |
          | (Flash & Pro Models)  |
          +-----------------------+
```

---

## 2. Process Specifications & Port Allocations

| Service Name | Runtime / Image | Port / Socket | Process Command | Health Probes | Responsibilities |
|---|---|---|---|---|---|
| **api** | Python 3.12 (`python:3.12-slim`) | `8000/tcp` | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4` | `/api/v1/health`<br>`/api/v1/live`<br>`/api/v1/ready` | Webhook ingestion, REST API, JWT auth, approval workflows, reporting. |
| **worker** | Python 3.12 (`python:3.12-slim`) | None (Internal) | `celery -A app.workers.celery_app worker --loglevel=info --concurrency=4` | Redis Celery ping | Asynchronous review orchestration, Tree-sitter AST parsing, LangGraph multi-agent execution, Adversarial Judge verification. |
| **web** | Node.js 22 (`node:22-alpine`) | `3000/tcp` | `node server.js` | HTTP GET `/` (200 OK) | Next.js 15 reactive operator dashboard: approvals, audit logs, policies, repo management. |
| **postgres** | PostgreSQL 16 (`postgres:16-alpine`) | `5432/tcp` | `postgres` | `pg_isready -U codeguard -d codeguard` | 27 relational tables across review state, findings, approvals, publications, and audit logs. |
| **redis** | Redis 7 (`redis:7-alpine`) | `6379/tcp` | `redis-server --appendonly yes --requirepass $REDIS_PASSWORD` | `redis-cli ping` | Celery task message broker, review queue, webhook delivery deduplication cache, rate limits. |

---

## 3. Trust Boundaries & Security Enclaves

CodeGuard enforces strict zero-trust operational boundaries:

### Boundary 1: Untrusted External Input (GitHub Webhooks & PR Payloads)
- **Axiom**: *All PR content (code diffs, author comments, commit messages, PR titles, descriptions) is passive untrusted data.*
- **Enforcement**:
  - HMAC-SHA256 signature verification on raw webhook body using constant-time comparison (`hmac.compare_digest`).
  - Webhook delivery ID replay tracking via Redis TTL cache.
  - Strict system prompt encapsulation with structural boundary tokens (`<<<UNTRUSTED PR CONTENT>>>`).
  - Prompt injection cannot escalate to tool execution or bypass the human approval gate.

### Boundary 2: Deterministic Code Intelligence Enclave
- **Components**: Tree-sitter multi-language grammar parsers, Unified Diff Parser, and `ChangedLineIndex`.
- **Enforcement**:
  - In-hunk vs. out-of-hunk line index mapping.
  - LLM agents are physically incapable of manufacturing or hallucinating line numbers that publish to GitHub.
  - The Adversarial Judge Gate 1 deterministically drops any candidate finding targeting unchanged or non-existent lines without querying the LLM.

### Boundary 3: AI Reasoning vs. Deterministic Authority
- **Axiom**: *AI agents provide untrusted candidate reasoning; deterministic backend algorithms provide binding authority.*
- **Enforcement**:
  - 5-Gate Adversarial Judge filter:
    - Gate 1: Diff line boundary validation.
    - Gate 2: Schema conformance and evidence verification.
    - Gate 3: False-positive suppression heuristics.
    - Gate 4: Security severity calibration.
    - Gate 5: Actionable recommendation criteria.

### Boundary 4: Zero-Trust Policy Engine Enclave (`app.core.policy`)
- **Enforcement**:
  - Consequential actions (`submit_review`, `post_comment`) are classified under `ActionRiskLevel.CONSEQUENTIAL` and require human approval.
  - Dangerous actions (`merge_pull_request`, `delete_repository`, `execute_shell`, `eval_code`, etc.) are hard-coded in `FORBIDDEN_OPERATIONS` and `FORBIDDEN_TOOL_ACTIONS` and rejected unconditionally.
  - Direct in-process evaluation executed by `PublicationService` before any GitHub API interaction.

### Boundary 5: Human Approval & Publication Binding
- **Enforcement**:
  - Reviews containing high/critical security findings require authorized human approval.
  - Approvals are cryptographically and statefully bound to the exact commit `head_sha`.
  - If a developer pushes a new commit to the PR after approval, commit drift is detected and publication is rejected as `STALE`.

---

## 4. End-to-End Operational Data Flow

```
[Developer pushes code / opens PR]
             │
             ▼
[GitHub Cloud sends Webhook Event (X-Hub-Signature-256)]
             │
             ▼ (API :8000)
1. Verify HMAC-SHA256 signature
2. Check Redis delivery replay cache
3. Enqueue review job in Celery via Redis
             │
             ▼ (Worker)
4. Fetch unified diff and target files from GitHub API
5. Tree-sitter AST parsing & ChangedLineIndex construction
6. LangGraph Multi-Agent execution:
   ├─ Comprehension Agent (Fast tier: gemini-2.5-flash)
   ├─ Specialist Agents (Security, Bug, Test, Performance: gemini-2.5-pro)
   └─ Synthesizer & Deduplicator
7. Adversarial Judge (5-gate evaluation)
8. Persist findings to PostgreSQL (Status: PENDING_APPROVAL or APPROVED)
             │
             ▼
[Dashboard Operator / Reviewer (:3000)]
9. Inspect findings, line diffs, and verification evidence
10. Submit Human Approval (Authorized role, anti-self-approval)
             │
             ▼ (API / Worker)
11. Sentinel Policy Engine verifies:
    ├─ Valid human approval present
    ├─ PR head SHA matches approval record
    └─ Diff line boundaries verified
12. Idempotent publication to GitHub via GitHub App API
13. Immutable record appended to `tool_execution_audits`
```

---

## 5. Storage & Persistence Architecture

1. **PostgreSQL 16 Database**:
   - Connection pool: SQLAlchemy async/sync pool (`DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=40`, `DB_POOL_TIMEOUT=30`).
   - Alembic migrations: 6 versioned revisions (`001` to `006`), 27 core tables.
   - Relational integrity: Strict Foreign Keys (`ON DELETE CASCADE` where bounded), Unique Constraints on composite keys, and B-tree indexes on lookup columns (`github_delivery_id`, `pr_id`, `head_sha`, `job_id`).

2. **Redis 7 Key-Value & Broker**:
   - Persistence: AOF (Append-Only File) enabled (`appendonly yes`).
   - Eviction: `volatile-lru` with memory limit (1024MB prod).
   - Keyspace:
     - `celery`: Task broker queue.
     - `webhook:delivery:<id>`: Replay suppression with 24-hour TTL.
     - `ratelimit:<ip/token>`: Leaky bucket rate limiting counters.

3. **Backup Storage**:
   - Gzip-compressed SQL snapshots (`scripts/backup_db.py`) with companion SHA-256 metadata.
   - Off-site rotation to encrypted cloud object storage (S3 / GCS).
