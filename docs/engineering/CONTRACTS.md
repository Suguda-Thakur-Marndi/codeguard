# CodeGuard — Architectural System Contracts (CONTRACTS.md)

**Document Status**: Active / Authoritative  
**Date**: September 17, 2026  
**Auditor**: Architect & Security Team

---

## 1. Executive Overview

This document formalizes the 10 critical architectural contracts governing CodeGuard. Every data transition across subsystem boundaries is strictly typed, validated at boundary entry, and guarded by explicit failure and idempotency semantics.

```
[GitHub Webhook]
       │
       ▼ Contract 1
[Review Job Service]
       │
       ▼ Contract 2
[Code Intelligence Engine]
       │
       ▼ Contract 3
[LangGraph Review Orchestrator]
       │
       ▼ Contract 4
[Specialist Agents (Security, Bug, Perf, Contract)]
       │
       ▼ Contract 5
[Adversarial Judge 5-Gate Pipeline]
       │
       ▼ Contract 6
[Validation Engine & Sandbox]
       │
       ▼ Contract 7
[Zero-Trust Policy Governance & Sentinel Policies]
       │
       ▼ Contract 8
[Human Authorization Lifecycle]
       │
       ▼ Contract 9
[GitHub Review Publisher]
       │
       ▼ Contract 10
[Immutable Audit Log System]
```

---

## 2. Contract 1: GitHub Webhook Ingestion → Review Job Creation

- **Input**:
  - Headers: `X-GitHub-Event`, `X-Hub-Signature-256`, `X-GitHub-Delivery`.
  - Body: JSON payload matching GitHub `pull_request` event (`opened`, `synchronize`, `reopened`).
- **Output**: `ReviewJob` record in database with status `PENDING`.
- **Validation**:
  - HMAC-SHA256 constant-time signature verification (`verify_github_signature`).
  - Delivery ID checked against replay cache (duplicate deliveries rejected with HTTP 200/409).
  - Timestamp within allowable window (+/- 300 seconds).
- **Failure Behavior**:
  - Signature mismatch: HTTP 401 Unauthorized.
  - Malformed payload: HTTP 422 Unprocessable Entity.
- **Authorization**: Valid GitHub Webhook Secret configured per installation.
- **Idempotency**: Duplicate delivery ID or re-delivered event returns existing review job ID without creating duplicate workers.

---

## 3. Contract 2: Review Job → Code Intelligence Engine

- **Input**: Repository Git Unified Diff string, base commit SHA, head commit SHA, file paths.
- **Output**:
  - `ChangedLineIndex`: Map of `{file_path: {"LEFT": [lines], "RIGHT": [lines]}}`.
  - `ASTChunkIndex`: List of AST function/class/method symbols intersected with changed lines.
- **Validation**:
  - Diff format compliant with unified diff standard.
  - File extensions checked against supported grammars (Python, JavaScript, TypeScript).
- **Failure Behavior**:
  - Syntax errors in modified files logged as warnings; parser produces partial AST or falls back to raw line diff. Whole review job never crashes.
- **Idempotency**: Pure deterministic function of the diff content.

---

## 4. Contract 3: Code Intelligence → LangGraph Review Orchestrator

- **Input**: `ReviewWorkflowState` initialized with PR metadata, changed files, line index, and AST context.
- **Output**: Fully traversed state graph with collected raw candidate findings.
- **Validation**: Strict Pydantic state schema (`ReviewWorkflowState`).
- **Failure Behavior**:
  - Graph nodes bounded by max iteration limits (preventing runaway cycles).
  - Specialist node exceptions isolated; remaining specialists complete execution.
- **Idempotency**: Checkpointed graph execution per unique `review_job_id`.

---

## 5. Contract 4: Orchestrator → Specialist Agents

- **Input**:
  - Filtered context slice (AST nodes, imports, callers, callees, diff lines).
  - Specialist system prompt with strict zero-shot / few-shot instructions.
- **Output**: List of `ReviewFinding` candidates.
- **Validation**:
  - Structured output validation conforming to `ReviewFinding` Pydantic schema:
    - `file_path`: str
    - `line_number`: int
    - `category`: `FindingCategory` (SECURITY, BUG, PERFORMANCE, CONTRACT)
    - `severity`: `FindingSeverity` (CRITICAL, HIGH, MEDIUM, LOW)
    - `description`: str
    - `evidence`: List of `EvidenceItem`
- **Failure Behavior**: Invalid JSON or malformed schema triggers up to 2 retries, then discards defective candidate.
- **Idempotency**: Driven by seed/temperature settings in model tier configuration.

---

## 6. Contract 5: Specialist Candidates → Adversarial Judge

- **Input**: Raw candidate `ReviewFinding` objects and verified `ChangedLineIndex`.
- **Output**: `JudgeDecision` (`decision`: "ACCEPTED" | "REJECTED", `reasons`: list[str], `gate_scores`: dict).
- **Validation**:
  - 5-Gate deterministic pipeline:
    1. Line boundary check against diff `RIGHT` lines.
    2. Category & severity constraint verification.
    3. Grounding code evidence presence.
    4. Actionable remediation presence.
    5. Duplicate candidate elimination.
- **Failure Behavior**: Any candidate failing any of the 5 gates is rejected with explicit audit trail reasons.
- **Idempotency**: Pure deterministic evaluation.

---

## 7. Contract 6: Adversarial Judge → Validation & Execution Sandbox

- **Input**: Accepted findings requiring dynamic validation or static verification.
- **Output**: `ValidationResult` (`is_valid`: bool, `evidence_captured`: dict, `execution_status`: str).
- **Validation**:
  - Safe allowlist: Only approved binaries (`pytest`, `python -m unittest`, `npm test`) permitted.
  - Strict blocking of dangerous shell operators: `|`, `;`, `&`, `sudo`, `curl`, `wget`, `rm`.
- **Failure Behavior**: Command timeout (max 30s) aborts process cleanly without worker leak. Non-zero exit code captured as failed validation.
- **Idempotency**: Executed in isolated temporary directory with guaranteed cleanup.

---

## 8. Contract 7: Validation Framework → Zero-Trust Policy Governance

- **Input**: Tool invocation request (`tool_name`, `arguments`, `caller_agent`).
- **Output**: Tool execution result or Policy Block rejection.
- **Validation**:
  - Tool existence in dynamic tool registry.
  - Arguments match Pydantic schema.
  - Tool risk classified against `TOOL_RISK_MAP` (`READ_ONLY`, `LOW_RISK`, `CONSEQUENTIAL`, `HIGH_RISK`, `FORBIDDEN`).
- **Failure Behavior**:
  - Forbidden tools (9 blocked operations) rejected instantly.
  - Consequential tools paused; routed to human approval queue.
- **Authorization**: Multi-tenant authorization verifies tool invocation within authorized organization scope.
- **Idempotency**: Tool execution tracked with unique `idempotency_key`.

---

## 9. Contract 8: Policy Engine → Human Authorization Lifecycle

- **Input**: Consequential tool call or publish action pending human approval.
- **Output**: `ApprovalRequest` record with status `PENDING`, `APPROVED`, or `REJECTED`.
- **Validation**:
  - Requester and approver must not be identical (anti-self-approval rule).
  - Approver must possess `ADMIN` or `SECURITY_LEAD` role.
  - PR `head_sha` at time of approval must match current PR `head_sha`.
- **Failure Behavior**:
  - Commit drift detected: approval invalidated (`STALE`), action blocked.
  - Approval expiration (TTL = 24 hours): status transitions to `EXPIRED`.
- **Idempotency**: Approving an already approved/rejected request is a no-op returning current state.

---

## 10. Contract 9: Human Approval → GitHub Review Publisher

- **Input**: Approved findings, PR metadata, and authorized token.
- **Output**: Published GitHub Review with inline diff comments.
- **Validation**:
  - All comments must align strictly with valid GitHub diff position and right-hand side line numbers.
  - Composite idempotency key computed: `hash(review_job_id + pr_id + head_sha + findings_hash)`.
- **Failure Behavior**:
  - GitHub 422 (Invalid position): Comment converted to top-level review body comment; review continues.
  - GitHub 5xx / 429: Exponential backoff with jitter (max 3 retries).
- **Idempotency**: Submitting the same review payload returns existing GitHub review ID without duplicate posting.

---

## 11. Contract 10: System Operations → Immutable Tool Execution & Audit Logging

- **Input**: Any security-sensitive event (tool execution, approval decision, publication, auth failure).
- **Output**: `ToolExecutionAudit` or audit log database entry.
- **Validation**:
  - All input/output strings automatically scrubbed for credentials, private keys, and tokens (`redact_sensitive_data`).
- **Failure Behavior**: Audit failure causes operation transaction to roll back; security operations cannot succeed if audit write fails.
- **Idempotency**: Immutable append-only records with unique UUID primary keys and UTC timestamps.
