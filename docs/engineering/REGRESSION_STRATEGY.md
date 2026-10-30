# CodeGuard — Multi-Tier Regression Prevention Strategy

**Document Status**: Active / Authoritative  
**Date**: September 17, 2026  
**Auditor**: Testing, Security & Architect Team

---

## 1. Core Principles & Zero-Regression Axiom

The CodeGuard engineering system operates under the **Zero-Regression Axiom**:
> *No code change, dependency update, or refactoring may degrade accuracy, bypass security boundaries, loosen test assertions, or invalidate existing contracts.*

Existing unit tests, acceptance scenarios, and empirical benchmarks serve as non-negotiable ground truth. If a change causes a test to fail, the code is defective, not the test.

---

## 2. Multi-Tier Defense Pyramid

```
Tier 1: Static Gates (Pre-Commit / Local)
  ├── Ruff Lint (205 files, 0 errors)
  ├── Pyright Static Typing (0 errors)
  └── TypeScript Compile Check (tsc --noEmit)

Tier 2: Fast Deterministic CI (Every PR)
  ├── 172 Automated Unit & Integration Tests (9.11s)
  ├── Tree-sitter Diff & Line Index Invariants
  ├── Adversarial Judge 5-Gate Deterministic Filters
  ├── Zero-Trust Policy Engine & 9 Forbidden Tool Rejections
  └── Frontend Next.js Production Build

Tier 3: Empirical Quality & Benchmark Regression (Merge Queue)
  ├── 12 Benchmark Scenarios Evaluated
  ├── Precision = 1.000, Recall = 1.000, F1 = 1.0000
  ├── Regression Detector: Delta F1 >= 0.0, Delta Precision >= 0.0
  └── Max Latency & Token Budget Caps

Tier 4: Acceptance & Operational Simulation (Nightly / Release)
  ├── 30 End-to-End Acceptance Scenarios (AC-001 to AC-030)
  ├── 6 Specialized System Audits (DB, Backup, Secret, Placeholder, Obs, Bench)
  └── Phase 12 Master Release Gate (22/22 PASS)
```

---

## 3. Subsystem Invariant Protections

### 1. Diff Mapping & Line Index Invariants
- **Invariant**: CodeGuard must never publish a review finding on an unchanged or invalid diff line.
- **Guard**: `ChangedLineIndex` and `UnifiedDiffParser` classify all changed lines into `LEFT` (old) and `RIGHT` (new) coordinates.
- **Regression Check**: Diffs with CRLF vs LF endings, multi-hunk single files, deleted files, and new files must maintain 100% line mapping precision.

### 2. AST Parsing & Syntax Error Resilience
- **Invariant**: Malformed, partial, or syntax-broken source code in PRs must never crash the review engine.
- **Guard**: Tree-sitter AST queries gracefully capture parse errors as `ERROR` syntax nodes and fall back to token/diff-level analysis.
- **Regression Check**: Automated fixtures with deliberately broken Python, TypeScript, and JavaScript syntax verify graceful degradation.

### 3. Adversarial Judge 5-Gate Verification
- **Invariant**: Speculative or hallucinated LLM findings must be rejected prior to publication.
- **Guard**: The 5-gate pipeline deterministically executes:
  1. Gate 1: Line Number Exists in Diff Right-Hand Side
  2. Gate 2: Category & Severity Strict Schema Match
  3. Gate 3: Grounded Supporting Code Evidence Present
  4. Gate 4: Actionable Remediation Guidance
  5. Gate 5: Semantic Deduplication against existing findings
- **Regression Check**: Candidate findings targeting line 8888 or ungrounded evidence are deterministically rejected without LLM invocation.

### 4. Zero-Trust Policy Engine & Forbidden Operations
- **Invariant**: AI agents must never execute unauthorized, destructive, or shell commands.
- **Guard**: Zero-Trust PolicyEngine intercepts all tool requests. All 9 dangerous operations (`execute_shell`, `eval_code`, `drop_database`, `modify_auth_policy`, `bypass_approval`, `access_raw_secrets`, `export_private_keys`, `impersonate_user`, `disable_audit_logging`) are unconditionally blocked.
- **Regression Check**: Every tool dispatch is verified against `TOOL_RISK_MAP`. Consequential tools require explicit, authenticated human approval.

### 5. Human Approval & Commit Drift Invalidation
- **Invariant**: An approved review cannot be published if the PR has been modified post-approval.
- **Guard**: Approvals are cryptographically bound to the PR's `head_sha`. If the author pushes new commits (`head_sha` changes), the approval is instantly transitioned to `STALE` and publication is blocked.
- **Regression Check**: AC-016 and AC-025 run as permanent regression guards.

---

## 4. Deterministic Testing vs Real Model Separation

To guarantee deterministic, ultra-fast CI runs while preserving real AI testing:

1. **Unit & Fast Integration Suites**:
   - Use `MockLLMProvider` returning structured, schema-compliant `ReviewFinding` models.
   - Use SQLite in-memory/file-backed engines and `fakeredis` where appropriate.
   - Run in under 10 seconds.
2. **Benchmark & Evaluation Suites**:
   - Run against curated, ground-truth benchmark datasets (`evaluation/datasets/v1`).
   - Measure empirical metrics (Precision, Recall, F1, Latency, Token Cost).
3. **Acceptance Suites**:
   - Exercise the complete production pipeline simulating GitHub webhooks, database persistence, and publication payloads.

---

## 5. Incident Reproduction Protocol

When any production or staging regression is detected:
1. **Isolate Symptom**: Record the exact input payload (PR diff, webhook JSON, tool call).
2. **Create Permanent Fixture**: Write a minimal reproducing test case in `apps/api/tests/test_regression_suite.py`.
3. **Verify Failure**: Run the test to confirm reproducible failure against the unpatched codebase.
4. **Apply Minimal Fix**: Implement the targeted fix without modifying unrelated code.
5. **Verify Green**: Confirm the regression test passes and all 172 existing tests remain passing.
6. **Log in Database**: Record the root cause, fix, and test reference in `docs/engineering/REGRESSION_HISTORY.md`.
