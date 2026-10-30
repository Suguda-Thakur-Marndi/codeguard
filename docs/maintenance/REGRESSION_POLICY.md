# CodeGuard — System Regression Prevention Policy

## 1. Prime Directive: Invariant Protection & Zero Test Weakening

CodeGuard enforces a zero-regression invariant: **Existing test assertions are authoritative contracts**. If code changes cause an existing test to fail, the implementation must be fixed; assertions must never be weakened or deleted to force a build to pass.

Every regression test added to the repository must protect a concrete security property, data integrity rule, or architectural invariant.

---

## 2. CI Regression Gates Architecture

The continuous integration pipeline (`.github/workflows/ci.yml`) is split into staged quality gates:

```text
GATE 1: Fast Static Analysis (Must complete in < 60s)
  - Ruff format & lint check (. tool.ruff)
  - TypeScript static type check (apps/web: tsc --noEmit)

GATE 2: Core Pytest Suite (Must complete in < 3m)
  - Backend pytest suite (apps/api/tests: unit, integration, security)

GATE 3: Frontend Compilation & Build (Must complete in < 2m)
  - Next.js 15 production build (apps/web: next build)
  - Static route generation verification (11 static/dynamic pages)

GATE 4: Container Packaging & Vulnerability Scan (Pre-deployment)
  - Docker build for API and Web containers
  - Trivy container security vulnerability scanner (Zero HIGH/CRITICAL)

GATE 5: Staging & Production Deployment Gates
  - Database migration idempotency check (alembic upgrade head)
  - Health and readiness verification (/api/v1/health, /api/v1/ready)
  - Human release authorization gate
```

### Invariant on Skipped Checks
Any skipped CI job must produce an explicit, justified status (`NOT TESTED — DEPENDENCY UNAVAILABLE`). Silent skips of release-critical gates are strictly prohibited.

---

## 3. The 6 Critical System Invariants

Permanent regression test suites protect these 6 system invariant domains:

### 3.1 GitHub App Integration Invariants
1. **Webhook Signatures**: Must be verified using HMAC-SHA256 (`X-Hub-Signature-256`) with constant-time equality checks; unauthenticated or malformed payloads must be rejected with HTTP 401.
2. **Duplicate Webhook Deduplication**: Duplicate delivery of the same `X-GitHub-Delivery` GUID within 24 hours must be idempotently acknowledged (`200 OK`) without triggering duplicate review jobs.
3. **Repository & PR Identity Validation**: Events targeting unregistered repositories or unauthorized organizations must be dropped.
4. **Valid Diff Line Mapping**: GitHub inline review comments must point strictly to lines modified within the PR diff hunks. Out-of-bounds line numbers must be converted to general PR summary comments.
5. **Idempotent Publication**: Multiple publication calls for the same review job must not generate duplicate comments on GitHub PRs.

### 3.2 Code Intelligence Invariants
1. **Symbol Boundary Integrity**: Tree-sitter AST parsing must preserve valid function, class, and method line boundaries across Python, JavaScript, and TypeScript.
2. **Safe Failure on Invalid Files**: Corrupted syntax, unsupported binary files, or oversized files (> 1MB) must fail safely without crashing the worker or leaking unhandled exceptions.
3. **Bounded Context Retrieval**: Symbol and reference retrieval must strictly respect token and line limits (`MAX_CONTEXT_TOKENS`) to prevent context window exhaustion.
4. **Stale Index Invalidation**: When a PR head commit changes, cached AST index keys must be invalidated; stale indexes must never masquerade as current commit data.

### 3.3 AI Review Invariants
1. **Strict Schema Validation**: All model outputs must parse against Pydantic schemas (`ReviewFinding`, `ReviewArtifact`); unparseable outputs must be safely rejected.
2. **Mandatory Evidence Binding**: Every finding must contain concrete code evidence (file path, line range, and code snippet). Fabricated findings without evidence must be discarded.
3. **Valid File & Line Validation**: Findings referencing non-existent files or line numbers outside the diff hunks must be rejected by the validation node.
4. **Bounded Agent Execution**: Multi-agent loops must enforce finite timeout and step limits to prevent runaway recursions or token consumption.
5. **No Fabricated Success**: A model timeout or failure must result in an explicit `FAILED` or `PARTIAL` job status, never a fake clean review.

### 3.4 Adversarial Judge Invariants
1. **Zero Hallucination Acceptance**: Confident model claims unsupported by code context must be rejected by the Hallucination Filter Gate.
2. **Distinct Root Cause Deduplication**: Findings addressing the same underlying bug across multiple lines must be clustered; distinct root causes must never be erroneously collapsed.
3. **Traceable Verification Decisions**: Every acceptance or rejection verdict must record the gate ID, rationale, and confidence score in the audit evaluation record.

### 3.5 Tool Execution & Policy Engine Invariants
1. **Server Authoritative Permissions**: The backend policy engine (`app.core.policy`) is authoritative; client prompts cannot override tool permission policies.
2. **Zero Consequential Agent Execution**: Consequential actions (`write`, `delete`, `deploy`) require explicit Human-in-the-Loop authorization.
3. **Tool Parameter Validation**: Tool arguments must be strictly validated against Pydantic schemas; unrecognized parameters or injection payloads must be rejected.
4. **Forbidden Actions Enforcement**: The 9 forbidden tool actions (shell execution, code eval, raw sockets, etc.) must remain blocked under all circumstances.

### 3.6 Human Approval & Publication Invariants
1. **Cryptographic Context Binding**: Human approval signatures must bind the specific `review_id`, `pr_id`, `head_sha`, and approver role using HMAC-SHA256.
2. **Stale Head SHA Publication Block**: If new commits are pushed to the PR (`head_sha` mismatch), previously granted approvals are invalidated and publication is blocked.
3. **Unauthorized Approver Rejection**: Users without `REVIEWER` or `ADMIN` roles cannot sign off on consequential publication actions.
4. **Audit Trail Immutability**: All approval and publication events must create immutable audit records in `audit_logs`.

---

## 4. Failure & Recovery Regression Testing

Automated failure recovery test suites (`apps/api/tests/test_failure_recovery.py`) continuously verify:
- **Worker Crash & Restart**: Tasks in progress when a Celery worker restarts must be detected as orphaned and rescheduled or marked failed cleanly.
- **Redis Connection Outage**: Database transactions must remain consistent if Redis drops; cache lookups must fall back gracefully to database queries.
- **PostgreSQL Transient Interruption**: SQLAlchemy pool must auto-reconnect on transient connection loss with exponential retry.
- **LLM Rate Limits & Timeouts**: Transient HTTP 429/503 errors from Gemini must trigger backoff retries without corrupting job state.
