# CodeGuard — Attack Surface Analysis

**Phase**: 15  
**Document**: Attack Surface Specification  
**Status**: Authoritative & Verified  

---

## 1. System Architecture Attack Surface Map

```
                                  [Internet / GitHub]
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
         [Webhooks / Ingestion]                         [Frontend Next.js UI]
         HMAC-SHA256 Auth                               Port: 3000
                  │                                               │
                  ▼                                               ▼
     [FastAPI API Gateway] ◄──────────────────────────────────────┘
     Port: 8000 (JWT Auth, RBAC, Rate Limiting, Input Validation)
                  │
        ┌─────────┼─────────────────────────┬─────────────────────────┐
        ▼         ▼                         ▼                         ▼
   [PostgreSQL] [Redis]             [Celery Worker]           [Policy Engine]
   Port: 5432   Port: 6379          (Review Pipeline)         (app.core.policy)
                                            │                         │
                                   ┌────────┴────────┐                │
                                   ▼                 ▼                ▼
                             [Gemini API]     [Sandbox Exec]   [GitHub REST API]
                             (AI Provider)    (Docker Container)(Publication)
```

---

## 2. Component-by-Component Attack Surface Analysis

### 1. Web Application Frontend (`apps/web/`)
- **Technology**: Next.js 15, React 19, Tailwind CSS.
- **Exposure**: Client-side web browser.
- **Threats**: Cross-Site Scripting (XSS), Cross-Site Request Forgery (CSRF), Clickjacking, Sensitive Token Storage.
- **Controls & Hardening**:
  - React automatic HTML output encoding prevents stored/reflected XSS.
  - No secrets or API keys embedded in client bundles.
  - Client state communicates with backend via authenticated `/api/v1/` REST routes using standard JSON payloads.
  - Visual layout, styles, and existing UX contracts strictly preserved.

---

### 2. FastAPI Gateway (`apps/api/app/api/`)
- **Technology**: FastAPI, Starlette, Pydantic v2, Uvicorn.
- **Exposure**: Public network / Reverse proxy (Port 8000).
- **Endpoints & Surfaces**:
  - `POST /api/v1/webhooks/github`: HMAC-SHA256 verified ingestion.
  - `GET/POST /api/v1/approvals`: Human authorization lifecycle.
  - `POST /api/v1/review-jobs/{id}/publish`: Review publication trigger.
  - `GET/POST /api/v1/organizations/{id}/policies`: Review policy management.
  - `GET /api/v1/repositories/{id}/context`: AST context retrieval.
- **Threats**: Broken Object Level Authorization (BOLA/IDOR), Broken Function Level Authorization (BFLA), SQL Injection, Path Traversal, Unauthenticated API access.
- **Controls & Hardening**:
  - `get_current_user_or_bypass` validates JWT cryptographic signature and expiration.
  - Multi-tenant query scoping enforced on all repository queries.
  - Path traversal checks (`FileFilter.is_safe_path`) reject upward directory movement (`../`) and absolute paths.
  - Role-Based Access Control (`ADMIN` role mandatory for policy changes; `REVIEWER` mandatory for approval actions).

---

### 3. Asynchronous Worker (`apps/api/app/workers/`)
- **Technology**: Celery, Redis message broker.
- **Exposure**: Internal network queue.
- **Threats**: Task injection, malicious job payload deserialization, worker resource starvation, retry storms.
- **Controls & Hardening**:
  - Standard JSON task serialization (pickle is forbidden).
  - Explicit job ID validation before execution.
  - Idempotency guard: active review jobs for the same PR cannot be duplicated.
  - Error containment: unhandled exceptions update database job status to `FAILED` with sanitized error summaries.

---

### 4. Database Layer (`apps/api/app/db/`)
- **Technology**: PostgreSQL 16, SQLAlchemy 2.0 ORM, Alembic migrations.
- **Exposure**: Internal container network (Port 5432).
- **Threats**: SQL Injection, unauthorized cross-tenant data access, database credential compromise, unauthorized schema alteration.
- **Controls & Hardening**:
  - Strict parameterized queries via SQLAlchemy ORM; zero raw string interpolation SQL.
  - Database migrations tracked deterministically through versioned Alembic scripts.
  - Connection credentials isolated via environment variables (`DATABASE_URL`).
  - Production invariants prevent default local passwords or localhost DB URLs.

---

### 5. Redis Queue & Cache (`redis:6379`)
- **Technology**: Redis 7.
- **Exposure**: Internal container network.
- **Threats**: Unauthorized queue inspection, cache poisoning, unauthenticated commands.
- **Controls & Hardening**:
  - Redis port is isolated within private Docker bridge network.
  - Only task metadata and job IDs are placed on the queue; sensitive credentials are never stored in cache keys.

---

### 6. GitHub External Integrations & Webhooks
- **Technology**: GitHub App REST API, Octokit / httpx client, HMAC-SHA256 webhooks.
- **Exposure**: Public HTTPS webhook receiver.
- **Threats**: Webhook forgery, replay attacks, GitHub token leakage, rate limit exhaustion.
- **Controls & Hardening**:
  - Constant-time HMAC-SHA256 signature verification (`hmac.compare_digest`).
  - `X-GitHub-Delivery` tracking and active job deduplication intercept replay attacks.
  - Automatic exponential backoff with jitter on GitHub API rate limits.
  - Webhook payload parsing handles unexpected, missing, or malformed fields safely.

---

### 7. Gemini LLM Integration (`apps/api/app/agents/llm/`)
- **Technology**: Google GenAI SDK / Gemini 2.5 Flash & Pro.
- **Exposure**: Outbound TLS to Google Cloud / AI Studio.
- **Threats**: Prompt injection, sensitive data leakage into training prompts, uncontrolled token consumption, non-deterministic structured output.
- **Controls & Hardening**:
  - Strict prompt formatting wrapping repository content as `<untrusted_repository_data>`.
  - Pydantic structured output parsing with type validation and confidence constraints.
  - Secret scrubbing (`sanitize_secrets`) strips tokens, keys, and authorization headers before prompt compilation.
  - Hard timeouts (`AGENT_TIMEOUT_SECONDS = 60s`) and bounded retries prevent retry loops.

---

### 8. Code Intelligence & AST Engine (`packages/code-intelligence/`)
- **Technology**: Tree-sitter C-bindings, Python unified diff parser, in-memory dependency graphs.
- **Exposure**: Local in-process parsing of repository diffs and files.
- **Threats**: ReDoS in diff parsing, memory exhaustion on huge files, arbitrary path traversal in file queries.
- **Controls & Hardening**:
  - `FileFilter` limits: max file size 500KB, max lines 5000, max AST nodes 20,000.
  - Binary file heuristic detection via null bytes and control character frequency.
  - Path canonicalization and traversal rejection (`FileFilter.is_safe_path`).

---

### 9. Adversarial Judge (`apps/api/app/agents/judge/`)
- **Technology**: 5-Gate deterministic and reasoning verification pipeline.
- **Exposure**: Pipeline decision stage before candidate findings are persisted.
- **Threats**: False positive pollution, hallucinated line coordinates, bypassed verification gates.
- **Controls & Hardening**:
  - Gate 1 (Diff Boundary): Deterministically drops any finding referencing lines outside changed diff hunks with zero token cost.
  - Gate 2 (Factuality): Inspects caller context and upstream guards to detect existing mitigations.
  - Gate 3 (Actionability): Rejects vague, cosmetic, or non-actionable suggestions.
  - Gate 4 (Severity): Downgrades over-inflated severity ratings.
  - Gate 5 (Execution): Optional sandbox dynamic execution.

---

### 10. Execution Sandbox (`apps/api/app/agents/validation/sandbox.py`)
- **Technology**: Docker container isolation / restricted sub-process runner.
- **Exposure**: Execution of test commands on repository code.
- **Threats**: Container breakout, host filesystem mutation, local network lateral movement, fork bombs, disk exhaustion.
- **Controls & Hardening**:
  - `network_mode="none"` blocks all outbound/inbound network traffic.
  - Read-only workspace mounts (`:ro`) prevent filesystem mutation.
  - Unprivileged non-root execution (`user="1000:1000"`, `no-new-privileges:true`).
  - Capabilities completely dropped (`cap_drop=["ALL"]`).
  - Strict command allowlist rejects shell metacharacters (`;`, `&&`, `||`, `|`, `` ` ``, `$`).
  - Strict resource constraints: 1.0 CPU, 512MB RAM, 64 PIDs, 30s timeout.

---

### 11. Zero-Trust Deterministic Policy Engine (`apps/api/app/core/policy.py`)
- **Technology**: In-process Python security policy engine with Pydantic validation.
- **Exposure**: Internal service boundary before GitHub review publication.
- **Threats**: Tool confusion, privilege escalation from low-risk to destructive actions, unapproved publication.
- **Controls & Hardening**:
  - Explicit action risk classification: `READ_ONLY`, `LOW_RISK`, `CONSEQUENTIAL`, `HIGH_RISK`.
  - Absolute forbidden operations blocklist: `merge_pull_request`, `repo_delete`, `arbitrary_shell`, `secret_access`, etc. unconditionally return `PolicyDecision.DENY`.
  - Human approval mandatory for all `CONSEQUENTIAL` and `HIGH_RISK` actions.
  - Strict validation that approval records match target repository and tenant organization.

---

### 12. GitHub Review Publication Layer (`apps/api/app/github/publisher.py`)
- **Technology**: Atomic review publisher via GitHub REST API.
- **Exposure**: Outbound publication to external GitHub PRs.
- **Threats**: Stale reviews posted to modified code, out-of-hunk inline comments, duplicate review spam, secret leakage in review comments.
- **Controls & Hardening**:
  - Head commit SHA freshness check: aborts with `STALE` if PR HEAD has moved.
  - Diff line coordinate verification: verifies every inline comment line against changed hunk indices.
  - Secret sanitization: scrubs credentials using high-confidence regex patterns.
  - Publication idempotency: composite key (`repo:pr:head_sha:job_id`) prevents duplicate publications.

---

### 13. Audit & Observability Telemetry (`apps/api/app/models/tool_audit.py`)
- **Technology**: Append-only PostgreSQL audit log, structured JSON telemetry.
- **Exposure**: Internal administrative queries.
- **Threats**: Audit log tampering, log injection via newlines, secret leakage in log fields.
- **Controls & Hardening**:
  - Immutable append-only audit trail: no `UPDATE` or `DELETE` API endpoints exist.
  - Redaction of sensitive fields prior to persistence.
  - JSON-formatted structured logging prevents newline log injection attacks.
