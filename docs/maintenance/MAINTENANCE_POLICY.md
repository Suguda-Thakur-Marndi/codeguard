# CodeGuard — Engineering Maintenance Policy

## 1. Prime Directive & Maintenance Philosophy

CodeGuard is an enterprise-grade agentic code review and security verification platform. As the system matures, the primary objective of maintenance engineering is **system stability, regression prevention, security posture preservation, and deterministic reliability**.

Maintenance follows the non-negotiable Engineering Hierarchy established in `AGENTS.md`:

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

### Core Invariants
1. **No UI/UX Redesigns**: Visual layouts, Tailwind classes, typography, component hierarchies, and navigation in `apps/web/` must remain unchanged during maintenance.
2. **No Business Logic Invention**: Never rewrite existing working logic or create ad-hoc abstractions. Maintain adversarial judge 5-gate filters, Zero-Trust PolicyEngine Sentinel policies, human approval lifecycles, and tenant isolation as designed.
3. **Never Weaken Tests**: Tests are authoritative evidence. If a test fails after an update, fix the implementation; never loosen assertions or delete tests.
4. **No Speculative Changes**: Code is modified only to fix verified bugs, address confirmed security advisories, or update dependencies following empirical validation.

---

## 2. Maintenance Cadence & Operating Schedule

| Cadence | Focus Area | Responsible Role | Verification Artifact |
| :--- | :--- | :--- | :--- |
| **Continuous (Per PR)** | CI Fast Checks: Lint, Type Check, Pytest, Frontend Build | CI Engine / Review Agent | GitHub Actions workflow status |
| **Weekly** | Dependency Advisories & Dependabot PR Review | Security / DevOps Agent | Dependabot PRs, `pip audit`, `npm audit` |
| **Monthly** | Database Migration & Connection Pool Health | Database Agent | Migration rollback tests, schema audit |
| **Quarterly** | Technical Debt Review & Deprecation Cleanup | Architect Agent | `docs/maintenance/TECHNICAL_DEBT.md` |

---

## 3. Specialized Maintenance Roles & Responsibilities

1. **Architect Agent**:
   - Evaluates system-wide impacts of proposed architectural updates.
   - Enforces minimal diff principles; rejects unnecessary refactorings.
2. **Backend Agent**:
   - Maintains FastAPI routes, Celery workers, and async service layers in `apps/api/`.
   - Ensures error handling and backward-compatible serialization.
3. **Frontend Agent**:
   - Maintains Next.js 15 web application in `apps/web/`.
   - Strictly preserves styling, colors, and layout while resolving client bugs.
4. **Database Agent**:
   - Oversees Alembic migrations (`apps/api/alembic/`), schema evolution, indexes, and connection pools.
   - Enforces expand-and-contract zero-downtime migration patterns.
5. **Security Agent**:
   - Reviews authentication, secret handling, tenant boundaries, and sandbox controls.
   - Conducts weekly dependency vulnerability triages.
6. **Policy & Governance Agent**:
   - Maintains zero-trust policy engine in `app.core.policy`.
   - Enforces the 9 forbidden actions and audit logging.
7. **AI / LangGraph Agent**:
   - Maintains LLM provider abstractions, prompt registry, and LangGraph review workflow.
8. **Code Intelligence Agent**:
   - Maintains Tree-sitter parsers, AST mappings, and symbol graphs in `packages/code-intelligence/`.
9. **Testing & QA Agent**:
   - Maintains unit and integration test suites (`pytest`).
   - Investigates and resolves any flaky or nondeterministic tests.
10. **DevOps / Release Agent**:
    - Manages CI/CD pipelines, Docker configurations, and release versioning.

---

## 4. Maintenance Change Criteria & Justification Standard

Every maintenance pull request must supply structured justification:

```text
MAINTENANCE PR CHECKLIST:
1. Target Component: [Backend | Frontend | DB | Policy | AI | DevOps]
2. Reason for Change: [Security Advisory | Bug Fix | Deprecation | Performance]
3. Empirical Evidence: [Error log, test failure, advisory CVE ID]
4. Minimal Diff Confirmed: [Yes / No]
5. No UI/UX Redesign: [Confirmed]
6. No Business Logic Invention: [Confirmed]
7. Tests Added or Updated (not weakened): [List of test files]
```

PRs lacking concrete evidence or containing speculative refactoring must be **REJECTED** by the Review Agent.

---

## 5. Emergency Hotfix Procedure

When a critical production defect or high-severity CVE is identified:

1. **Branch**: Branch hotfix directly from `main` (`hotfix/YYYYMMDD-<issue-slug>`).
2. **Reproduce**: Write a targeted regression test reproducing the failure before altering code.
3. **Fix**: Implement the minimal code change to satisfy the regression test.
4. **Validate**:
   - Run targeted test: `pytest apps/api/tests/test_<name>.py`
   - Run full suite: `pytest apps/api/tests`
5. **Peer Review**: Minimum 2 maintainers (or Security Agent + Domain Specialist) must sign off.
6. **Deploy**: Deploy via CI/CD staging gate, execute smoke tests, then deploy to production with immediate rollback plan in place.
