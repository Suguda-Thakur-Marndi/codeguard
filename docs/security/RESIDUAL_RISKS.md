# CodeGuard — Residual Risk Register (RESIDUAL_RISKS.md)

In compliance with the Zero-Bypass security principles of CodeGuard, this document registers all documented residual risks, their operational impact, reasons for their current status, active mitigations, and required future roadmap actions.

No security status may claim "100% secure" or hide residual risks.

---

## 1. Registered Residual Risks

### RISK-01: LLM Non-Determinism & Zero-Day Prompt Injection Evasion
- **Risk**: Advanced semantic adversarial jailbreaks (e.g., recursive encoding, multi-lingual token splitting) might bypass raw system prompt framing.
- **Affected Component**: `apps/api/app/agents/llm/gemini.py`, `apps/api/app/agents/orchestrator/`
- **Reason Unresolved**: LLM reasoning is fundamentally stochastic and non-deterministic; prompt boundaries alone cannot mathematically prevent all novel jailbreaks.
- **Current Mitigation**: Strict separation of concerns. AI reasoning is strictly treated as untrusted draft generation. Deterministic post-LLM validation layers (Adversarial Judge 5-Gate filter, Pydantic schema validation, and deterministic policy engine) independently enforce all security boundaries. Even if an LLM is completely jailbroken, it cannot publish reviews or invoke high-risk tools without valid, human-signed approval records.
- **Required Future Action**: Integrate an adversarial embedding classifier (e.g., Llama-Guard or NeMo Guardrails) in front of the Gemini prompt ingestion pipeline.

---

### RISK-02: Ephemeral Local Workspace Isolation vs. Production Docker Sandboxing
- **Risk**: Sandboxed validation currently relies on OS subprocess containment with command allowlisting and timeout enforcement rather than microVMs (Firecracker / gVisor).
- **Affected Component**: `apps/api/app/agents/validation/sandbox.py`
- **Reason Unresolved**: Full microVM deployment requires hypervisor hardware virtualization not present in all local developer or test runner environments.
- **Current Mitigation**: Hardened command allowlist (`pytest`, `ruff`, `bandit`, `tree-sitter` only); dangerous shell operators (`;&|><$` and backticks) are strictly rejected; execution runs under unprivileged worker accounts with 30-second timeout containment and automatic process tree termination.
- **Required Future Action**: Deploy gVisor (runsc) or Firecracker container isolation for worker task execution in Kubernetes staging and production deployments.

---

### RISK-03: Development Auth Bypass Environment Misconfiguration
- **Risk**: If `DEV_AUTH_BYPASS` is inadvertently set to `true` in a production deployment, unauthenticated requests could gain developer access.
- **Affected Component**: `apps/api/app/core/security.py`
- **Reason Unresolved**: Development ease requires a fast local mock authentication mechanism when external OAuth/IdP providers are not configured.
- **Current Mitigation**: Hard-coded dual-check in `get_current_user_or_bypass`: `if settings.DEV_AUTH_BYPASS and settings.APP_ENV != "production"`. When `APP_ENV=production`, `DEV_AUTH_BYPASS` is unconditionally ignored and raises HTTP 401 Unauthorized.
- **Required Future Action**: Add CI/CD deployment linter that validates Docker environment variables to ensure `DEV_AUTH_BYPASS` is not defined or is set to `false` in production manifests.

---

### RISK-04: Upstream GitHub API Rate Limiting During Massive Monorepo Scans
- **Risk**: Very large pull requests (>100 files or >10,000 lines) may exhaust GitHub API rate limits during diff fetching and AST chunk indexing.
- **Affected Component**: `apps/api/app/services/github_service.py`, `packages/code-intelligence/`
- **Reason Unresolved**: GitHub enforces hourly rate limits per installation token (5,000 requests/hour).
- **Current Mitigation**: ChangedLineIndex filters out non-source files (`.md`, images, lockfiles, minified bundles); diff parsing is capped at 10MB; AST parsing only processes files containing actual changed hunks.
- **Required Future Action**: Implement secondary Redis caching for repository tree blobs and install GitHub App token rotation pools across multiple app IDs.

---

### RISK-05: In-Memory Webhook Delivery Deduplication Reset on Worker Restart
- **Risk**: If Redis is degraded and worker falls back to local memory for delivery ID tracking, worker restart could allow replay of recent webhooks.
- **Affected Component**: `apps/api/app/api/v1/endpoints/webhooks.py`
- **Reason Unresolved**: Network partition or Redis maintenance window requires graceful degradation.
- **Current Mitigation**: Webhook event processing triggers idempotent review workflow runs; review job creation uses unique database constraint `uq_pull_request_head_sha` on PR reviews, preventing duplicate concurrent reviews for the same head commit.
- **Required Future Action**: Ensure multi-zone Redis Cluster with persistent AOF (Append-Only File) logging for zero delivery-window loss during failover.

---

## 2. Residual Risk Governance & Acceptance

All registered residual risks have been reviewed by the Security Architecture and Red-Team engineering roles. None of the residual risks represent an active or exploitable bypass of the core security gates (Authentication, Authorization, Tenant Isolation, Sentinel Policy, Approval Context Binding, or Diff Line Boundaries).

**Residual Risk Status**: **CONDITIONAL ACCEPTANCE**
All critical attack vectors are fully mitigated by deterministic backend controls. Residual risks are managed under defense-in-depth operational runbooks.
