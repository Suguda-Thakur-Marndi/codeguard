# CodeGuard — System Architecture & Component Overview

**Document ID**: `DOC-ARCH-SYSTEM-01`  
**Application**: CodeGuard  
**Version**: `1.0.0`  
**Base Commit**: `085615eb45da36135a7374b614e3705ad9ca2468`  
**Last Verified**: 2026-09-29  

---

## 1. System Topology & Architectural Philosophy

CodeGuard provides automated, adversarial-resistant GitHub Pull Request code reviews under strict zero-trust governance and human-in-the-loop authorization.

```
                           +------------------------+
                           |  GitHub Cloud Webhook  |
                           +-----------+------------+
                                       | HMAC-SHA256
                                       v
                           +------------------------+
                           |  FastAPI Backend API   | <---> [ PostgreSQL 16 ]
                           |  (:8000, Ingress Auth) |       (27 Relational Tables)
                           +-----------+------------+
                                       |
                   Enqueues Task       | Reads/Writes State
                                       v
                           +------------------------+
                           |     Redis 7 Broker     |
                           |  (Task Queue & Cache)  |
                           +-----------+------------+
                                       |
                   Subscribes Worker   |
                                       v
+-----------------------------------------------------------------------------------+
| Celery Asynchronous Review Worker Subsystem                                       |
|                                                                                   |
|  1. Tree-sitter AST & Diff Indexer  --> Extracts modified hunks & enclosing AST   |
|  2. Semantic Context Ranker         --> Token-budgeted caller/reference assembly  |
|  3. LangGraph Orchestrator          --> Parallel dispatch across 6 specialists   |
|  4. Adversarial Judge (5 Gates)     --> Drops hallucinations & downgrades severity|
|  5. Execution Sandbox               --> Syntactic & behavioral safety validation  |
+-----------------------------------------------------------------------------------+
        |                                                           |
        | Evaluates Policy under Zero-Trust                         | Outbound Inference
        v                                                           v
+------------------------+                                  +-----------------------+
|  Zero-Trust Policy     |                                  |   Google Gemini API   |
|  Engine (app.core.pol) |                                  | (Flash / Pro Models)  |
+-----------+------------+                                  +-----------------------+
            |
            | Consequential Actions Require Signature
            v
+------------------------+       Publishes Review       +---------------------------+
|  Human Approval Gate   | ---------------------------> |   GitHub PR Inline Review |
| (Next.js Dashboard)    |                              |   (Idempotent Multi-Line) |
+------------------------+                              +---------------------------+
```

---

## 2. Component Specifications (The 16 Core Subsystems)

### 2.1 Frontend Dashboard (`apps/web`)
1. **Responsibility**: Provides operator interface for reviewing AI findings, authorizing consequential actions, inspecting audit logs, and configuring organization review policies.
2. **Entry Point**: `apps/web/app/layout.tsx` and `apps/web/app/page.tsx` (Next.js 15 App Router).
3. **Dependencies**: React 19, Tailwind CSS, Lucide icons, `apps/web/lib/api.ts` typed client.
4. **Inputs/Outputs**: Ingests user credentials / operator actions; emits REST API calls to `:8000`.
5. **Failure Handling**: Displays toast error notifications and error boundary fallbacks on API degradation.
6. **Testing**: `npm run lint` and `npm run build` (standalone production compile with strict TypeScript).
7. **Configuration**: `NEXT_PUBLIC_API_URL` in `apps/web/.env.local`.

---

### 2.2 Backend Core API (`apps/api`)
1. **Responsibility**: Ingests webhooks, authenticates JWT sessions, hosts CRUD endpoints for reviews, approvals, findings, and serves health/liveness probes.
2. **Entry Point**: `apps/api/app/main.py` (`fastapi_app`).
3. **Dependencies**: FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0.
4. **Inputs/Outputs**: HTTP REST requests; emits structured JSON responses and Celery task dispatches.
5. **Failure Handling**: Global exception handlers convert unhandled exceptions to RFC 7807 Problem Details; logs causally linked traces with `X-Request-ID`.
6. **Testing**: `apps/api/tests/test_api_endpoints.py`, `apps/api/tests/test_health.py`.
7. **Configuration**: `app.core.config.Settings` loaded from `.env`.

---

### 2.3 Authentication & Authorization (`app.core.security`)
1. **Responsibility**: Issues and validates cryptographically signed JWT tokens, enforces RBAC roles (`ADMIN`, `REVIEWER`, `MEMBER`), and protects against dev bypass leaks.
2. **Entry Point**: `app.core.security.create_access_token` and `app.api.v1.deps.get_current_user`.
3. **Dependencies**: `pyjwt[crypto]`, `passlib[bcrypt]`, `cryptography`.
4. **Inputs/Outputs**: Ingests `Authorization: Bearer <token>`; outputs authenticated `User` context with role.
5. **Failure Handling**: Rejects invalid signatures or expired tokens with `HTTP 401 Unauthorized`; fail-fast startup rejects `DEV_AUTH_BYPASS=true` in `APP_ENV=production`.
6. **Testing**: `verify_phase16.py` Gate 15 and Gate 16, `verify_phase15.py` Gate 07.
7. **Configuration**: `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DEV_AUTH_BYPASS` in `Settings`.

---

### 2.4 GitHub Integration Client (`app.github.client`)
1. **Responsibility**: Authenticates as a GitHub App via short-lived installation access tokens generated from an RSA private key. Fetches PR metadata, diffs, and commits.
2. **Entry Point**: `app.github.client.GitHubAppClient`.
3. **Dependencies**: `httpx`, `pyjwt[crypto]`.
4. **Inputs/Outputs**: Ingests `installation_id`, `repo_name`, `pr_number`; outputs raw unified diff strings, file contents, and commit metadata.
5. **Failure Handling**: Retries on HTTP 502/503; respects `Retry-After` headers on HTTP 429 rate limits.
6. **Testing**: `test_webhooks.py`, `test_github_publisher.py` with mock HTTP transports.
7. **Configuration**: `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY` in `Settings`.

---

### 2.5 Webhook Processing & Replay Guard (`app.services.webhook_service`)
1. **Responsibility**: Validates GitHub webhook HMAC-SHA256 signatures, filters relevant events (`pull_request.opened`, `synchronize`), drops replays, and enqueues review jobs.
2. **Entry Point**: `app.api.v1.endpoints.webhooks.handle_github_webhook`.
3. **Dependencies**: `hmac`, `hashlib`, Redis cache.
4. **Inputs/Outputs**: Ingests raw HTTP request payload and `X-Hub-Signature-256` header; outputs `202 Accepted` and enqueues Celery task.
5. **Failure Handling**: Rejects invalid signatures with `HTTP 401`; drops duplicate delivery IDs via 60-second Redis TTL cache.
6. **Testing**: `apps/api/tests/test_webhooks.py` (10 test cases), AC-017.
7. **Configuration**: `GITHUB_WEBHOOK_SECRET` in `Settings`.

---

### 2.6 Database & Relational Repositories (`app.db`)
1. **Responsibility**: Manages connection pooling, transaction lifecycles, and relational persistence across 27 tables.
2. **Entry Point**: `app.db.session.get_db` and repository classes in `app.db.repositories`.
3. **Dependencies**: SQLAlchemy 2.0, psycopg2 / sqlite3, Alembic.
4. **Inputs/Outputs**: Ingests domain model instances; outputs persisted entities with foreign keys and unique constraints.
5. **Failure Handling**: Automatic rollback on unhandled database exceptions; pool pre-ping handles dead connection recycling.
6. **Testing**: `verify_phase16.py` Gate 04, `scripts/run_acceptance_suite.py` AUDIT-DB.
7. **Configuration**: `DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` in `Settings`.

---

### 2.7 Celery Review Worker (`app.workers`)
1. **Responsibility**: Asynchronous execution of the multi-agent review pipeline outside the HTTP request-response cycle.
2. **Entry Point**: `app.workers.tasks.execute_review_job`.
3. **Dependencies**: Celery 5.4, Redis broker, LangGraph orchestrator.
4. **Inputs/Outputs**: Ingests `job_id: str`; executes multi-agent pipeline; updates `ReviewJob` record to `COMPLETED` or `FAILED`.
5. **Failure Handling**: Captures worker crashes cleanly in the database; retries transient network failures with exponential backoff.
6. **Testing**: `apps/api/tests/test_worker.py`, AC-029.
7. **Configuration**: `REDIS_URL`, `CELERY_TASK_ALWAYS_EAGER` in `Settings`.

---

### 2.8 Queue & Idempotency Store (`Redis 7`)
1. **Responsibility**: High-speed in-memory broker for Celery queues, webhook deduplication replay keys, and review job publication locks.
2. **Entry Point**: `app.core.redis_client`.
3. **Dependencies**: `redis-py` (or `fakeredis` in local test suites).
4. **Inputs/Outputs**: Key-value operations, atomic `SETNX`, queue push/pop.
5. **Failure Handling**: In local test mode, falls back gracefully to `fakeredis` or in-memory dictionary if Redis is offline.
6. **Testing**: `verify_phase16.py` Gate 06.
7. **Configuration**: `REDIS_URL` in `Settings`.

---

### 2.9 Code Intelligence & Tree-Sitter Parsers (`packages/code-intelligence`)
1. **Responsibility**: Parses multi-language source code (Python, JS, TS) into ASTs, extracts enclosing entity boundaries for diff hunks, builds repository symbol graphs, and deterministically ranks context.
2. **Entry Point**: `code_intelligence.parsers.get_parser`, `code_intelligence.context.rank_context`.
3. **Dependencies**: `tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`, `unidiff`.
4. **Inputs/Outputs**: Ingests raw git diff and file contents; outputs structured `ParsedDiff`, `SymbolGraph`, and ranked `ContextChunk` list within token budget.
5. **Failure Handling**: Falls back to line-based regex hunk extraction if AST parsing encounters unsupported syntax or syntax errors.
6. **Testing**: `apps/api/tests/test_tree_sitter_parsers.py`, `test_context_ranker.py`, `test_diff_parser.py`.
7. **Configuration**: Hardcoded language grammars and token limits in `code_intelligence.config`.

---

### 2.10 AI Multi-Agent Orchestrator (`app.agents.orchestrator`)
1. **Responsibility**: Manages the LangGraph `StateGraph` review lifecycle: Comprehension, Risk Routing, parallel Specialist Agent dispatch, and Synthesis.
2. **Entry Point**: `app.agents.orchestrator.graph.create_review_graph`.
3. **Dependencies**: `langgraph`, Pydantic v2 schemas.
4. **Inputs/Outputs**: Ingests `ReviewState` containing diff and context; outputs aggregated list of raw candidate `ReviewFinding` models.
5. **Failure Handling**: If an individual specialist agent fails, other specialists continue; the failure is logged without aborting the entire review.
6. **Testing**: `apps/api/tests/test_orchestrator.py`, `test_agents.py`.
7. **Configuration**: `AGENT_MAX_CONCURRENCY` in `Settings`.

---

### 2.11 Gemini LLM Provider (`app.agents.llm.gemini`)
1. **Responsibility**: Executes structured output LLM inference against Google Gemini models, enforcing JSON schema adherence, retry backoff, and token tracking.
2. **Entry Point**: `app.agents.llm.gemini.GeminiLLMProvider`.
3. **Dependencies**: `google-genai` SDK, `httpx`.
4. **Inputs/Outputs**: Ingests prompt strings and Pydantic response schemas; outputs validated Pydantic model instances with `TokenUsage`.
5. **Failure Handling**: Exponential backoff with jitter on HTTP 429/503; falls back to mock provider in test mode (`LLM_PROVIDER=mock`).
6. **Testing**: `apps/api/tests/test_llm_provider.py`, AC-020, AC-021.
7. **Configuration**: `GEMINI_API_KEY`, `GEMINI_MODEL_FAST`, `GEMINI_MODEL_REASONING` in `Settings`.

---

### 2.12 Adversarial Verification Judge (`app.agents.judge`)
1. **Responsibility**: Intercepts AI hallucinations, verifies findings against diff boundaries and caller guards, filters non-actionable suggestions, and down-calibrates inflated severity.
2. **Entry Point**: `app.agents.judge.adversarial_judge.AdversarialJudge.evaluate_findings`.
3. **Dependencies**: Tree-sitter AST, execution sandbox.
4. **Inputs/Outputs**: Ingests candidate findings list; outputs filtered, verified, and deduplicated findings list.
5. **Failure Handling**: Gate evaluation is fail-safe; if verification of an optional check fails, the finding is conservatively flagged for human operator review.
6. **Testing**: `apps/api/tests/test_judge.py`, `test_deduplication.py`, AC-008.
7. **Configuration**: Judge thresholds in `app.agents.judge.config`.

---

### 2.13 Zero-Trust Deterministic Policy Engine (`app.core.policy`)
1. **Responsibility**: Deterministic zero-trust policy engine enforcing hardcoded forbidden actions blocklists (9 operations), tool parameter schemas, and immutable audit logging. Operates in-process without MCP network overhead.
2. **Entry Point**: `apps/api/app/core/policy.py` (`PolicyEngine`).
3. **Dependencies**: Pydantic, SQLAlchemy audit logging models.
4. **Inputs/Outputs**: Ingests evaluated action inputs and principal contexts; outputs `PolicyDecision` (allow / deny / approval required).
5. **Failure Handling**: Unconditionally blocks high-risk operations; enforces human approval checks for consequential actions.
6. **Testing**: `apps/api/tests/test_security_resilience.py`, `test_security_audit_phase15.py`, AC-022.
7. **Configuration**: Hardcoded non-negotiable security invariants.

---

### 2.14 Human Approval Gate (`app.services.approval_service`)
1. **Responsibility**: Enforces human-in-the-loop authorization for consequential actions. Binds approvals to exact `head_sha` commits and rejects stale approvals upon commit drift.
2. **Entry Point**: `app.services.approval_service.ApprovalService`.
3. **Dependencies**: PostgreSQL `approval_requests` table, JWT auth.
4. **Inputs/Outputs**: Ingests operator decision (`APPROVE` / `REJECT`); updates approval state and transitions review to publishable.
5. **Failure Handling**: Blocks auto-self-approval by AI agents; blocks publication if `pr.head_sha != approval.head_sha`.
6. **Testing**: `apps/api/tests/test_approvals.py`, AC-016, AC-024, AC-025.
7. **Configuration**: `APPROVAL_EXPIRY_MINUTES_DEFAULT` in `Settings`.

---

### 2.15 GitHub Review Publisher (`app.github.publisher`)
1. **Responsibility**: Atomically posts approved findings as inline review comments to the GitHub Pull Request using GitHub's Pull Request Review API.
2. **Entry Point**: `app.github.publisher.GitHubReviewPublisher.publish_review`.
3. **Dependencies**: `app.github.client.GitHubAppClient`, regex secret scrubbers.
4. **Inputs/Outputs**: Ingests approved `ReviewJob` and findings; outputs GitHub review with multi-line comments.
5. **Failure Handling**: Idempotent re-runs skip duplicate postings; redacts bearer tokens and private keys from comment bodies prior to submission.
6. **Testing**: `apps/api/tests/test_github_publisher.py`, AC-028.
7. **Configuration**: Handled via `Settings`.

---

### 2.16 Logging, Tracing & Secret Scrubbing (`app.core.logging`)
1. **Responsibility**: Emits structured JSON logs causally correlated by `trace_id` and `request_id`, automatically redacting sensitive credentials.
2. **Entry Point**: `app.core.logging.setup_logging` and `app.core.logging.redact_sensitive_data`.
3. **Dependencies**: Python standard `logging`, regex scrubbers.
4. **Inputs/Outputs**: Log records; outputs sanitized JSON log streams.
5. **Failure Handling**: Scrubber errors fall back to raw message masking rather than crashing the calling process.
6. **Testing**: `test_security_resilience.py`, `verify_phase16.py` Gate 03, AUDIT-SEC.
7. **Configuration**: `LOG_LEVEL` in `Settings`.
