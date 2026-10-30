# CodeGuard — Technical Debt Registry

## 1. Governance & Prioritization Standard

Technical debt in CodeGuard is managed with empirical rigor. Functional, well-tested code is **never rewritten simply because another framework or style is fashionable**. Technical debt is cataloged, evaluated against operational risk, and scheduled for remediation based on concrete engineering ROI.

---

## 2. Active Technical Debt Inventory

### TD-001: SQLite / PostgreSQL Dual-Dialect Compatibility Layer
- **Component**: `apps/api/alembic/`, `app/core/database.py`, `apps/api/tests/`
- **Description**: Fast, isolated unit and integration test execution uses in-memory SQLite (`sqlite:///:memory:`), while staging and production rely on PostgreSQL 16 with native JSONB, concurrent indexing, and foreign key cascades.
- **Impact**: Code and Alembic migrations maintain dialect-aware conditional branching (`dialect.name == "sqlite"` vs `"postgresql"`).
- **Evidence**: `apps/api/alembic/versions/` files contain explicit SQLite fallback clauses for JSON columns and non-transactional DDL.
- **Risk**: Low. SQLite provides 18.96s hermetic test execution across 221 tests. Potential risk of PostgreSQL-specific syntax slips if untested against Postgres.
- **Suggested Remediation**: Retain SQLite for fast developer inner loops; configure dedicated PostgreSQL test service container in GitHub Actions CI for pre-merge validation.
- **Dependencies**: GitHub Actions runner compute allocation.
- **Status**: **ACCEPTED ARCHITECTURAL COMPROMISE**

---

### TD-002: Host Environment Docker Linux Engine Dependency
- **Component**: `docker-compose.yml`, `infra/`, container builds
- **Description**: Developer workstations running native Windows without active WSL2 / Docker Desktop Linux daemons cannot execute local multi-container compose builds or local Trivy scans.
- **Impact**: Container image compilation and vulnerability scanning are executed in GitHub Actions CI (`ubuntu-latest`) rather than pre-commit local hooks.
- **Evidence**: Local Docker socket `//./pipe/dockerDesktopLinuxEngine` unavailable during local Windows execution.
- **Risk**: Low. Containerfiles (`apps/api/Dockerfile`, `apps/web/Dockerfile`) are verified and cleanly build in CI.
- **Suggested Remediation**: Document WSL2 setup in `docs/maintenance/MAINTENANCE_RUNBOOK.md` while treating CI as the authoritative container builder.
- **Dependencies**: Developer workstation OS configuration.
- **Status**: **MONITORED**

---

### TD-003: Synthetic / Mock Fallback Layer for External Providers
- **Component**: `apps/api/app/services/llm_provider.py`, `apps/api/app/services/github_publisher.py`
- **Description**: When external cloud credentials (`GEMINI_API_KEY`, `GITHUB_PRIVATE_KEY`) are not present in local or CI environments, service clients fall back to deterministic synthetic providers.
- **Impact**: Test suites execute with 100% determinism and zero API cost, but external API contract drift (e.g. Gemini deprecations or GitHub schema changes) must be caught in staging.
- **Evidence**: All 226 tests pass offline in < 7s without external network calls.
- **Risk**: Low to Medium. External cloud API changes could occur without failing offline tests.
- **Suggested Remediation**: Run weekly scheduled staging smoke tests against live sandbox APIs with dedicated non-production keys.
- **Dependencies**: Cloud API quota and test credentials.
- **Status**: **CONTROLLED / TESTED IN STAGING**

---

### TD-004: Frontend Lint Script Uses Pure TypeScript Compiler
- **Component**: `apps/web/package.json`
- **Description**: In `apps/web/package.json`, `"lint": "tsc --noEmit"` is configured. Static analysis runs through TypeScript's compiler (`tsc`) rather than ESLint CLI.
- **Impact**: TypeScript compiler catches 100% of syntax errors, type mismatches, and undefined properties in 0.8s, but custom stylistic ESLint formatting rules are not run during `npm run lint`.
- **Evidence**: `apps/web/package.json:9`: `"lint": "tsc --noEmit"`. Next.js build (`next build`) runs type checking and compiles cleanly.
- **Risk**: Very Low. Code quality and type safety are enforced by TypeScript compiler and Next.js build.
- **Suggested Remediation**: Align ESLint 9 flat config dependencies with Next.js 15 and React 19 when upstream configurations reach full parity.
- **Dependencies**: Next.js and ESLint upstream compatibility.
- **Status**: **LOW PRIORITY / ACCEPTED**
