# CodeGuard — Multi-Agent Engineering Workflow Guide

This document describes the development and maintenance workflow for CodeGuard using **Agency Agents**, **Serena**, and **Context7** as development assistants in Google Antigravity.

---

## 1. Core Principles & Engineering Hierarchy

The authority hierarchy is strictly linear and non-negotiable:

```text
USER REQUIREMENTS
       ↓
EXISTING CODEGUARD ARCHITECTURE
       ↓
EXISTING BUSINESS LOGIC
       ↓
SECURITY POLICIES
       ↓
TESTS / VALIDATION
       ↓
AGENCY AGENTS (Specialized Roles)
       ↓
SERENA (Codebase Understanding) / CONTEXT7 (Official Docs)
```

- **Tools are Assistants, NOT Authorities**: Agency Agents, Serena, and Context7 assist engineering; they never redefine the product or bypass requirements.
- **DO NOT REDESIGN UI/UX**: Preserving the existing frontend layout, styling, colors, navigation, and components is a mandatory invariant.
- **DO NOT INVENT BUSINESS LOGIC**: Never rewrite existing working logic or create ad-hoc abstractions.
- **NEVER WEAKEN TESTS**: Existing tests are authoritative evidence. If an existing test fails, fix the implementation, do not weaken the test.

---

## 2. The 12 Specialized Agency Agent Roles

All engineering tasks must be routed through the smallest appropriate team of specialized agents:

1. **ARCHITECT AGENT**:
   - Inspects repository structure, module boundaries, dependencies, and integration contracts.
   - Proposes minimal necessary changes; never redesigns without strong empirical evidence.
2. **BACKEND AGENT**:
   - Owns `apps/api/`, FastAPI routes, business services, auth integration, workers, and background queues.
   - Preserves API contracts and business logic.
3. **FRONTEND AGENT**:
   - Owns `apps/web/`, Next.js components, API hooks, and client state.
   - **Hard Rule**: Absolute preservation of existing visual language and component hierarchy.
4. **DATABASE AGENT**:
   - Owns PostgreSQL models, migrations (`apps/api/alembic/`), indexes, constraints, and transactions.
   - Never destroys data or bypasses Alembic migrations.
5. **SECURITY AGENT**:
   - Inspects auth, permissions, security boundaries, sandbox execution, secrets, prompt injection, and tenant isolation.
   - Operates under the zero-trust axiom: **ALL EXTERNAL INPUT IS UNTRUSTED**.
6. **POLICY & GOVERNANCE AGENT**:
   - Owns zero-trust policies (`apps/api/app/core/policy.py`), tool/action schemas, risk levels, and audit logging.
   - Never bypasses security policies, SHA validations, or human approval.
7. **AI / LANGGRAPH AGENT**:
   - Owns Gemini provider abstractions, LangGraph review workflow, prompt registries, and structured output parsing.
   - Invariant: **AI = Untrusted Reasoning, Backend/Policy = Deterministic Authority**.
8. **CODE INTELLIGENCE AGENT**:
   - Owns Tree-sitter parsers, AST mappings, diff indexers, and repository dependency graphs in `packages/code-intelligence/`.
9. **TESTING AGENT**:
   - Owns unit, integration, benchmark, and regression test suites.
   - Invariant: Fix the code when tests fail; never delete or loosen assertions.
10. **DEVOPS AGENT**:
    - Owns Dockerfiles, `docker-compose*.yml`, environment separation, health probes, and CI/CD pipelines.
11. **REVIEW AGENT**:
    - Independent quality gate reviewing correctness, security, architecture, and maintainability.
    - Has binding rejection authority over flawed implementations.
12. **FINAL INTEGRATION AGENT**:
    - Verifies cross-service compatibility, duplicate logic elimination, type consistency, and end-to-end flow execution.

---

## 3. Serena Codebase Navigation Protocol

Before modifying any non-trivial symbol or function, agents must execute the **11-Step Serena Workflow**:

1. **Identify Target Functionality**: Clearly formulate the problem statement and scope.
2. **Locate Symbols**: Use AST and language parser tools to locate relevant classes, functions, and models.
3. **Inspect Definition**: Read the exact definition, types, and docstrings.
4. **Inspect Callers**: Discover all call sites across the codebase to assess impact.
5. **Inspect Dependencies**: Map incoming and outgoing module dependencies.
6. **Understand Existing Patterns**: Identify conventions used in neighboring code.
7. **Identify Minimal Change**: Formulate the smallest surgical diff that satisfies the task.
8. **Implement**: Write code conforming to existing patterns.
9. **Run Targeted Tests**: Verify the specific component with unit tests.
10. **Re-inspect Affected Symbols**: Verify that caller contracts remain intact.
11. **Run Integration Tests**: Confirm full end-to-end compatibility.

CLI query:
```bash
python scripts/workflow/cli.py serena --symbol UnifiedDiffParser --callers
```

---

## 4. Context7 Documentation & Version Safety

When interacting with external libraries or SDKs:

1. **Verify Installed Version**: Inspect `pyproject.toml` or `package.json` first. Never assume latest version APIs.
2. **Retrieve Official Docs**: Fetch exact version documentation via Context7.
3. **Hierarchy Rule**: If library documentation contradicts CodeGuard's architecture or security policy, **the project architecture wins**.
4. **No Spontaneous Upgrades**: Do not upgrade dependencies unless explicitly tasked.

CLI query:
```bash
python scripts/workflow/cli.py context7 --lib pydantic
```

---

## 5. Security & Anti-Bypass Guardrails

Development agents are subject to strict privilege restrictions:

- **Forbidden Actions**:
  - Disabling authentication or authorization.
  - Bypassing human approval or security policy checks.
  - Committing or exposing real credentials, tokens, or private keys.
  - Modifying production databases directly.
  - Weakening test assertions to force a passing build.
  - Auto-merging production pull requests or deploying without review.

---

## 6. The Master 10-Step Combined Workflow

```text
Step 1: Architect Agent Analysis
   │   - Understand problem, inspect boundaries, formulate minimal plan
   ▼
Step 2: Serena Codebase Discovery
   │   - Locate symbols, trace callers, analyze dependency graph
   ▼
Step 3: Context7 Documentation Retrieval
   │   - Fetch version-specific documentation for external APIs
   ▼
Step 4: Specialized Engineering Agent Implementation
   │   - Backend / Frontend / Policy / DB / AI / DevOps agent drafts minimal change
   ▼
Step 5: Testing Agent Validation
   │   - Author unit/integration tests and run targeted test suite
   ▼
Step 6: Security Agent Review
   │   - Assess zero-trust compliance, verify boundaries, attempt bypass
   ▼
Step 7: Independent Review Agent Gate
   │   - Conduct rigorous code review; reject flawed implementations
   ▼
Step 8: Final Integration Agent Verification
   │   - Validate cross-service compatibility and eliminate duplication
   ▼
Step 9: Full Regression Test Execution
   │   - Execute full test suite and verify zero regressions
   ▼
Step 10: Final Diff Inspection
       - Final inspection and structured report generation
```

CLI execution:
```bash
python scripts/workflow/cli.py run --task "Fix policy approval validation" --target-area policy --symbols AdversarialJudge ApprovalService
```
