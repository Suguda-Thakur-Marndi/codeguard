# CodeGuard — Multi-Agent Engineering Architecture & Guidelines (AGENTS.md)

This repository enforces a structured, specialized multi-agent engineering workflow designed for development and maintenance.

## 1. Prime Directive & Engineering Hierarchy

The authority hierarchy is strictly linear and non-negotiable:

```
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

## 2. Specialized Agency Agent Roles

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

1. Identify target functionality.
2. Locate relevant symbols via AST/Index.
3. Inspect definitions and docstrings.
4. Inspect callers and call-sites.
5. Inspect upstream and downstream dependencies.
6. Understand existing patterns and conventions.
7. Identify the minimal necessary diff.
8. Implement the change.
9. Run targeted tests.
10. Re-inspect affected symbols for unintended regressions.
11. Run integration tests.

---

## 4. Context7 Documentation & Version Safety

When interacting with external libraries or SDKs:

1. **Verify Installed Version**: Inspect `pyproject.toml` or `package.json` first. Never assume latest version APIs.
2. **Retrieve Official Docs**: Fetch exact version documentation via Context7.
3. **Hierarchy Rule**: If library documentation contradicts CodeGuard's architecture or security policy, **the project architecture wins**.
4. **No Spontaneous Upgrades**: Do not upgrade dependencies unless explicitly tasked.

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

## 6. Structured Communication & Output Schema

All specialized agents must provide their findings and proposals in the structured format:

```text
ROLE: <Agent Name>
TASK: <Task Description>

UNDERSTOOD REQUIREMENT:
<Detailed requirement summary>

FILES INSPECTED:
- <file_1>
- <file_2>

FILES CHANGED:
- <file_1>

IMPLEMENTATION:
<Technical rationale and implementation summary>

TESTS:
<Commands and test results>

SECURITY CONSIDERATIONS:
<Security analysis and threat mitigations>

RISKS:
<Potential regressions or failure modes>

BLOCKERS:
<Any unresolved dependencies or questions>

FINAL STATUS: <SUCCESS | REJECTED | BLOCKED>
```
