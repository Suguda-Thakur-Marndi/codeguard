# CodeGuard — Security Architecture & Threat Model (STRIDE)

**Phase**: 15  
**Status**: Comprehensive / Authoritative  
**Classification**: Engineering Security Architecture Document  

---

## 1. Prime Directive & Engineering Security Axiom

In CodeGuard, the fundamental security axiom is:

> **ALL EXTERNAL AND AI-GENERATED INPUT IS UNTRUSTED DATA.**  
> The Large Language Model (Gemini) is an untrusted reasoning engine, NOT a security authority.  
> The Frontend is a user interface, NOT a security boundary.  
> Security authorization, policy enforcement, data isolation, and human approval lifecycle are governed strictly and deterministically by application backend logic and immutable database records.

```
USER REQUIREMENTS
       ↓
EXISTING CODEGUARD ARCHITECTURE
       ↓
EXISTING BUSINESS LOGIC
       ↓
SECURITY POLICIES (Zero-Bypass Deterministic PolicyEngine)
       ↓
TESTS / EMPIRICAL VALIDATION
```

---

## 2. Trust Boundary Map & Data Flow Architectures

CodeGuard operates across five explicit trust boundaries. Each boundary defines trusted inputs, untrusted inputs, authentication, authorization, validation, output handling, logging, and failure behaviors.

### Trust Boundary 1: User / Frontend &rarr; API &rarr; Database
```
[User Browser] (Untrusted Origin)
       │
       │ HTTP / HTTPS (Session JWT / Bearer Token)
       ▼
[FastAPI Gateway / Core Security]
       │ Authentication (JWT Decode, Secret Verification)
       │ Role Authorization (MEMBER, REVIEWER, ADMIN)
       ▼
[Service & Repository Layer]
       │ Organization / Tenant Scoping (WHERE org_id = ...)
       ▼
[PostgreSQL Database] (Isolated Multi-Tenant Schema)
```

- **Trusted Input**: Server-signed JWT claims (`sub`, `exp`, `role`, `organization_id`), server-computed timestamps.
- **Untrusted Input**: HTTP headers, query parameters, JSON request payloads, URL path parameters, cookie values.
- **Authentication**: HMAC-SHA256 JWT decoding with mandatory `sub` and `exp` validation. In development/test mode, controlled token bypass is permitted; strictly prohibited in `production`.
- **Authorization**: Role-Based Access Control (RBAC):
  - `MEMBER`: Read-only access to tenant repositories, pull requests, findings, and publications.
  - `REVIEWER`: Authorized to approve or reject pending human approval requests for the user's organization.
  - `ADMIN`: Authorized to update organization review policies, manage repository configurations, and perform administrative operations.
- **Validation**: Strict Pydantic v2 schemas; path traversal sanitization via `FileFilter.is_safe_path`.
- **Output Handling**: Automatic credential scrubbing via `sanitize_secrets`; strict model serialization excluding database connection strings and sensitive metadata.
- **Logging**: Structured JSON telemetry with `request_id`, client IP, endpoint, and status code. No bearer tokens or passwords logged.
- **Failure Behavior**: Rejection with HTTP 401 (Unauthorized), 403 (Forbidden), or 400 (Bad Request). Internal exceptions masked in production.

---

### Trust Boundary 2: GitHub &rarr; Webhook Ingestion &rarr; Backend Worker
```
[GitHub Platform]
       │
       │ HTTP POST (X-Hub-Signature-256, X-GitHub-Delivery)
       ▼
[Webhook Endpoint: /api/v1/webhooks/github]
       │ Constant-Time HMAC-SHA256 Signature Verification
       ▼
[WebhookService]
       │ Idempotency Verification (Active Job & Delivery Deduplication)
       ▼
[Celery Background Worker] (Redis Queue)
```

- **Trusted Input**: None prior to cryptographic verification.
- **Untrusted Input**: Raw HTTP body, headers, event metadata, commit SHAs, PR descriptions.
- **Authentication**: Constant-time HMAC-SHA256 verification using `GITHUB_WEBHOOK_SECRET`.
- **Authorization**: GitHub App installation ID mapping to registered `Organization` records.
- **Validation**: Cryptographic signature match, JSON parsing, Pydantic `GitHubWebhookPayload` model validation.
- **Output Handling**: HTTP 202 Accepted (queued) or HTTP 200 OK (ping / ignored).
- **Logging**: Structured telemetry capturing `delivery_id`, `event_type`, and target repository.
- **Failure Behavior**: Immediate HTTP 401 Unauthorized for invalid signatures; HTTP 400 for malformed JSON; duplicate deliveries return HTTP 200 with `status: "ignored"`.

---

### Trust Boundary 3: PR Source Code &rarr; Code Intelligence &rarr; LLM &rarr; Adversarial Judge
```
[PR Source Code / Diffs] (Untrusted Repositories)
       │
       ▼
[Code Intelligence Layer]
       │ UnifiedDiffParser & Tree-sitter AST Extraction
       │ ChangedLineIndex Mapping (Strict changed hunk coordinates)
       ▼
[Gemini AI Provider / Specialist Agents]
       │ PromptRegistry Data Delimiters (Strictly UNTRUSTED DATA)
       ▼
[Candidate Findings]
       │
       ▼
[Adversarial Judge 5-Gate Filter]
       ├── Gate 1: Diff Boundary Conformity (Must match ChangedLineIndex)
       ├── Gate 2: Contextual Factuality (Existing guard detection)
       ├── Gate 3: Actionability Verification (Concrete vs vague)
       ├── Gate 4: Severity & Confidence Audit
       └── Gate 5: Sandbox Behavioral Execution (Optional verification)
```

- **Trusted Input**: Canonical changed line index computed directly from git diff hunks.
- **Untrusted Input**: Pull request title, body, commit messages, comments, source code files, variable names, function names, imported module contents.
- **Authentication**: Service-level API key for Gemini provider.
- **Authorization**: Read-only repository indexing bound to specific tenant repository IDs.
- **Validation**:
  - All prompt templates wrap PR contents in explicit data tags: `<untrusted_repository_data>`.
  - Adversarial Judge enforces 5 deterministic gates. Any finding referencing an out-of-hunk line number is rejected at Gate 1 without token expenditure.
- **Output Handling**: Pydantic structured output parsing with type constraints and confidence bounds `[0.0, 1.0]`.
- **Logging**: LLM token consumption, latency, and audited decision telemetry.
- **Failure Behavior**: Malformed LLM responses trigger retry up to `AGENT_MAX_RETRIES` before falling back to empty findings list.

---

### Trust Boundary 4: PublicationService &rarr; PolicyEngine &rarr; Approval &rarr; GitHub
```
[Agent / Worker]
       │ Review Output (Findings)
       ▼
[PublicationService]
       │ Action Request (submit_review)
       ▼
[PolicyEngine (In-Process)]
       ├── 1. Forbidden Operations Check (merge, delete, shell -> DENY)
       ├── 2. Risk Classification (READ_ONLY, LOW, CONSEQUENTIAL, HIGH)
       ├── 3. Organization Policy Evaluation
       └── 4. Human Approval Verification (Bound to HEAD SHA, Repo, & Tenant)
       ▼
[GitHubReviewPublisher]
       │ Re-verify Head SHA freshness & Diff Line coordinates
       │ Sanitize secrets ([REDACTED_SECRET])
       ▼
[GitHub REST API] (create_pull_request_review)
```

- **Trusted Input**: Human approval records in PostgreSQL (`status == "APPROVED"`), verified head commit SHA.
- **Untrusted Input**: Agent findings, candidate comment texts, suggested diff lines.
- **Authentication**: In-process method calls with typed `Principal` roles.
- **Authorization**: Deterministic `PolicyEngine` evaluating principal role, organization policy, and attached approval credentials.
- **Validation**:
  - `PolicyEngine` verifies approval status, expiration (`now < expires_at`), anti-self-approval (`not is_ai_agent`), head commit SHA binding, repository binding, and tenant organization binding.
  - `GitHubReviewPublisher` validates inline comment lines against git diff hunks.
- **Output Handling**: Idempotent composite publication key (`repo:pr:head_sha:job_id`).
- **Logging**: Immutable append-only audit trail in `tool_execution_audit` table.
- **Failure Behavior**: Unauthorized requests return `PolicyDecision.DENY`; stale commits raise `PublicationStatus.STALE`; invalid lines abort publication.

---

### Trust Boundary 5: Review Execution &rarr; Sandbox Execution Container
```
[Verification Orchestrator]
       │ Test Scenario Command (pytest, npm test, ruff)
       ▼
[ExecutionSandbox]
       ├── Command Allowlist Verification (No shell operators: ;, &&, ||, |, `)
       ├── Resource Limits (1.0 CPU, 512MB RAM, 64 PIDs, 30s Timeout)
       ├── Isolation (network_mode="none", read-only root mount)
       └── Privileges (User 1000:1000, cap_drop=["ALL"], no-new-privileges)
       ▼
[Ephemeral Docker Container / Process] (Destroyed in finally block)
```

- **Trusted Input**: System command allowlist (`pytest`, `ruff`, `eslint`, `npm test`).
- **Untrusted Input**: Repository test files, source files, environment variables.
- **Authentication**: Local Docker daemon socket or local sub-process execution.
- **Authorization**: Only allowlisted commands without shell metacharacters can be executed.
- **Validation**: Regex and token parsing preventing shell injection, redirection, command chaining, or subshells.
- **Output Handling**: Truncated output summary limited to `SANDBOX_MAX_OUTPUT_BYTES` (64KB).
- **Logging**: Execution status, exit code, duration, and runtime evidence.
- **Failure Behavior**: Timeout terminates container after 30 seconds; non-zero exit code recorded as `FAIL`; teardown guaranteed in `finally` block.

---

## 3. Threat Actor Model

CodeGuard explicitly defenses against seven distinct threat actor profiles:

| Threat Actor | Description | Capabilities | Primary Targets | Key Defenses |
| :--- | :--- | :--- | :--- | :--- |
| **Actor A: Malicious PR Author** | External or internal contributor submitting hostile code | Controls PR diff, commit messages, comments, variable/function names, README | Prompt injection, prompt leakage, tool invocation | Data delimiters in prompts, deterministic PolicyEngine, Adversarial Judge Gate 1 & 2 |
| **Actor B: Unauthorized Authenticated User** | Valid user with MEMBER role attempting privilege escalation | Valid JWT credentials, valid session | Horizontal/vertical escalation, modifying policies, approving reviews | Server-side RBAC, strict tenant filtering on all repository queries |
| **Actor C: Compromised Reviewer** | Legit reviewer account compromised by adversary | REVIEWER role permissions | Stale approvals, approving unauthorized actions, cross-tenant approvals | Anti-stale SHA verification, cross-tenant approval rejection, immutable audit logging |
| **Actor D: Malicious Internal Caller** | Compromised microservice or internal caller | Access to internal services | Dangerous operations (`repo_delete`, `arbitrary_shell`, `merge_pull_request`) | PolicyEngine classification, hardcoded forbidden tools blocklist |
| **Actor E: Compromised Integration** | Malicious or spoofed external GitHub delivery | Can send forged webhooks or modified payloads | Duplicate reviews, triggering CI exhaustion, spamming reviews | HMAC-SHA256 constant-time verification, delivery deduplication, active job idempotency |
| **Actor F: Hostile Test / Sandbox Payload** | PR containing fork bombs, diskfillers, or escape exploits | Executes inside test verification sandbox | Host filesystem escape, network lateral movement, host container control | `network_mode="none"`, read-only mounts, `cap_drop=["ALL"]`, PID limit 64, 30s timeout |
| **Actor G: Prompt Injection Attacker** | Direct & Indirect prompt injection crafter | Crafts adversarial payloads in imported modules, comments, descriptions | Hijacking agent instructions, exfiltrating secrets, bypassing human approval | Model is untrusted; PolicyEngine & ApprovalService operate completely outside LLM boundary |

---

## 4. Security Asset Inventory

| Asset Name | Sensitivity | Storage Location | Access Mechanism | Encryption / Protection | Retention | Authorized Roles | Exposure Mitigation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GitHub App Private Key** | CRITICAL | Secret Manager / Env | Backend App initialization | In-flight / Env variable | Active lifecycle | System Worker | Never committed; redacted from logs |
| **GitHub Webhook Secret** | CRITICAL | Secret Manager / Env | Webhook HMAC verification | In-flight / Env variable | Active lifecycle | API Gateway | Constant-time HMAC comparison |
| **Gemini API Key** | HIGH | Secret Manager / Env | AI Provider initialization | In-flight / Env variable | Active lifecycle | AI Agent | Never passed to client or external services |
| **JWT Secret Key** | HIGH | Secret Manager / Env | Session token generation | In-flight / Env variable | Active lifecycle | Auth Service | Min 32 bytes; validated at startup |
| **Database Credentials** | CRITICAL | Secret Manager / Env | SQLAlchemy connection pool | In-flight / Env variable | Active lifecycle | DB Engine | Internal network only; non-root user |
| **Source Code & ASTs** | HIGH | Local disk / PostgreSQL | Code Intelligence Engine | Isolated DB tables / Vol | PR review lifetime | Tenant Members | Tenant-scoped database queries |
| **Findings & Evidence** | HIGH | PostgreSQL database | ReviewFindingRepository | Row-level tenant scope | Organization audit | Tenant Reviewers | Judge verification; scrubbed secrets |
| **Approval Records** | CRITICAL | PostgreSQL database | ApprovalService | Append-only / SHA bound | Permanent audit | Tenant Reviewers | Anti-stale SHA check; anti-agent |
| **Audit Logs** | CRITICAL | PostgreSQL database | ToolExecutionAudit repo | Append-only immutability | Permanent audit | Tenant Admins | Automatic secret scrubbing |

---

## 5. STRIDE Threat Analysis Across Components

### 1. Spoofing (Identity & Authenticity)
- **Threat**: Attacker sends forged GitHub webhooks or impersonates human reviewers.
- **Mitigation**:
  - HMAC-SHA256 verification using `hmac.compare_digest` prevents webhook spoofing.
  - Signed JWT tokens with expiration prevents user spoofing.
  - Human approvals require explicit user credentials; AI agent principal IDs are strictly forbidden from approving actions.

### 2. Tampering (Data Integrity)
- **Threat**: Modifying PR diffs, changing approval requests, or altering audit logs.
- **Mitigation**:
  - Git commit SHAs provide cryptographic content verification; any change to PR HEAD invalidates pending approvals.
  - Audit records in `tool_execution_audit` are append-only.
  - `ChangedLineIndex` anchors every inline comment to real git diff lines.

### 3. Repudiation (Accountability)
- **Threat**: Reviewer denies approving a high-risk review; agent denies publishing a comment.
- **Mitigation**:
  - Every approval records `approved_by`, `resolved_at`, and rationale in PostgreSQL.
  - All tool executions are logged with `duration_ms`, `principal_id`, `tool_name`, `authorization_decision`, and parameters.

### 4. Information Disclosure (Confidentiality)
- **Threat**: Leakage of API keys, tokens, or cross-tenant pull requests.
- **Mitigation**:
  - `sanitize_secrets` regex scrubs Bearer tokens, GitHub personal access tokens (`ghp_`, `ghs_`), and Gemini API keys.
  - Multi-tenant database queries enforce `organization_id` filters.
  - Stack traces and internal database schemas are suppressed in production.

### 5. Denial of Service (Availability)
- **Threat**: Huge diffs, replayed webhooks, infinite agent loops, or fork bombs in sandbox.
- **Mitigation**:
  - Delivery ID and active review job deduplication blocks webhook replay storms.
  - FileFilter enforces max file size (500KB), max lines (5000), and max AST nodes (20,000).
  - Sandbox limits CPU (1.0), RAM (512MB), processes (64), and execution time (30s).
  - LangGraph review workflows enforce strict recursion limits and timeouts.

### 6. Elevation of Privilege (Authorization)
- **Threat**: MEMBER role updates policies; low-risk tool escalates to `merge_pull_request`.
- **Mitigation**:
  - Server-side RBAC checks in `PolicyService.update_policy` enforce `ADMIN` role.
  - `PolicyEngine` enforces hardcoded denylist over destructive operations.
  - Human-in-the-loop approval gate is mandatory for all high-risk or consequential reviews.
