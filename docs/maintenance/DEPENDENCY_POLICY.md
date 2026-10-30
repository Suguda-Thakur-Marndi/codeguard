# CodeGuard — Dependency Inventory & Management Policy

## 1. Dependency Inventory

This inventory captures all direct dependencies across the CodeGuard ecosystem, documenting installed versions, runtime contexts, lockfile locations, and update governance rules.

### 1.1 Backend Core & API (`apps/api/pyproject.toml`)

| Package Name | Specified Version | Direct/Transitive | Purpose | Runtime Context | Lockfile / Pinning |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `fastapi` | `>=0.111.0` | Direct | High-performance ASGI REST Framework | `api` container | Compatible release |
| `uvicorn[standard]` | `>=0.30.0` | Direct | ASGI Production Web Server | `api` | Standard extras |
| `pydantic` | `>=2.7.0` | Direct | Data validation & settings management | `api`, worker | V2 core models |
| `pydantic-settings`| `>=2.3.0` | Direct | Environment configuration parsing | `api`, worker | Environment bindings |
| `sqlalchemy` | `>=2.0.30` | Direct | Asynchronous & synchronous ORM | `api`, worker | 2.0 style syntax |
| `alembic` | `>=1.13.1` | Direct | Schema migrations engine | `api` migration job | Version-controlled DDL |
| `psycopg2-binary` | `>=2.9.9` | Direct | PostgreSQL driver for migrations & pooling | `api`, worker | Production DB driver |
| `redis` | `>=5.0.4` | Direct | Redis client for Celery broker & caching | `api`, worker | Async/sync Redis |
| `celery` | `>=5.4.0` | Direct | Asynchronous task queue worker | worker process | Distributed review jobs |
| `httpx` | `>=0.27.0` | Direct | Async HTTP client for external integrations | `api`, worker | GitHub & Gemini HTTP |
| `cryptography` | `>=42.0.7` | Direct | HMAC, SHA-256, and approval cryptography | `api`, worker | Critical security core |
| `pyjwt[crypto]` | `>=2.8.0` | Direct | JWT verification for user & GitHub App auth | `api` auth | Cryptographic tokens |
| `python-dateutil` | `>=2.9.0` | Direct | ISO-8601 date parsing & retention timing | `api`, worker | Date utility |
| `tree-sitter` | `>=0.24.0` | Direct | AST parsing engine for code intelligence | `api`, worker, pkg | Native C binding |
| `tree-sitter-python`| `>=0.25.0`| Direct | Python grammar binding | `api`, worker, pkg | AST parsing |
| `tree-sitter-javascript`|`>=0.25.0`| Direct | JavaScript grammar binding | `api`, worker, pkg | AST parsing |
| `tree-sitter-typescript`|`>=0.23.0`| Direct | TypeScript / TSX grammar binding | `api`, worker, pkg | AST parsing |
| `unidiff` | `>=1.0.0` | Direct | Unified diff parsing & hunk line mapping | `api`, worker, pkg | Patch analysis |
| `langgraph` | `>=0.2.0` | Direct | Multi-agent state machine orchestrator | `api`, worker | Review pipeline graph |
| `google-genai` | `>=0.1.0` | Direct | Official Google Gemini GenAI SDK | `api`, worker | LLM reasoning engine |

### 1.2 Development & Test Suite (`apps/api/pyproject.toml[dev]`)

| Package Name | Specified Version | Purpose | Runtime Context |
| :--- | :--- | :--- | :--- |
| `pytest` | `>=8.2.1` | Master test runner | Local / CI test execution |
| `pytest-asyncio` | `>=0.23.7` | Asynchronous test execution plugin | Local / CI test execution |
| `pytest-mock` | `>=3.14.0` | Mocking and monkeypatching fixtures | Local / CI test execution |
| `fakeredis` | `>=2.23.2` | In-memory Redis simulation for hermetic testing | Local / CI test execution |
| `ruff` | `>=0.4.5` | High-speed linter and formatter | Local / CI linting |
| `mypy` | `>=1.10.0` | Static type checker | Local / CI type checking |

### 1.3 Frontend Web Application (`apps/web/package.json`)

| Package Name | Installed Version | Type | Purpose |
| :--- | :--- | :--- | :--- |
| `next` | `^15.2.0` (15.5.25 runtime) | Direct | App Router React Framework |
| `react` | `^19.0.0` | Direct | UI library |
| `react-dom` | `^19.0.0` | Direct | DOM rendering |
| `clsx` | `^2.1.1` | Direct | Conditional CSS class manipulation |
| `tailwind-merge` | `^3.0.2` | Direct | Tailwind class deduplication |
| `lucide-react` | `^1.16.0` | Direct | UI iconography |
| `typescript` | `^5.8.2` | Dev | Static type analysis |
| `tailwindcss` | `^3.4.17` | Dev | Utility-first CSS engine |
| `postcss` | `^8.5.3` | Dev | CSS preprocessing |
| `autoprefixer` | `^10.6.0` | Dev | CSS vendor prefixing |
| `eslint` | `^9.39.5` | Dev | JavaScript / TypeScript linting |
| `eslint-config-next`| `^16.3.5` | Dev | Next.js linting rules |

### 1.4 Container Base Images & CI Actions

| Asset | Specified Image / Action | Purpose |
| :--- | :--- | :--- |
| **API & Worker Container** | `python:3.12-slim` | Debian-based slim Python 3.12 image |
| **Web Container** | `node:22-alpine` | Alpine-based Node.js 22 LTS image |
| **Redis Service** | `redis:7-alpine` | Alpine-based Redis 7 container |
| **CI Checkout** | `actions/checkout@v4` | Git repository checkout |
| **CI Setup Python** | `actions/setup-python@v5` | Python 3.12 installation with pip caching |
| **CI Setup Node** | `actions/setup-node@v4` | Node.js 22 installation with npm caching |
| **CI Buildx** | `docker/setup-buildx-action@v3` | Multi-platform container build engine |
| **CI Docker Build** | `docker/build-push-action@v5` | Image packaging and tagging |
| **CI Security Scan** | `aquasecurity/trivy-action@master` | Container CVE security scanner |

---

## 2. Safe Dependency Update Protocol

Whenever a dependency requires updating (due to a security advisory, bug fix, or end-of-life deprecation), engineers must follow this sequence:

1. **Inspect Release Notes**: Read the upstream changelog and migration guide for breaking changes.
2. **Check Compatibility**: Cross-reference minimum Python (`>=3.11`) and Node (`>=20`) version requirements.
3. **Review Breaking Changes**: Identify deprecated functions, renamed arguments, or altered default behaviors.
4. **Update Smallest Set**: Update only the single target package or minimal related group. Do not run indiscriminate global upgrades.
5. **Regenerate Lockfiles**: For Node.js, run `npm install --package-lock-only` in `apps/web/`.
6. **Run Formatting & Linting**: Run `ruff check .` across the workspace and `npm run lint` in `apps/web/`.
7. **Run Type Checks**: Run `npm run lint` (`tsc --noEmit`) and verify Python typing.
8. **Run Unit Tests**: Run `pytest apps/api/tests -k unit`.
9. **Run Integration Tests**: Run full pytest backend test suite (`pytest apps/api/tests`).
10. **Review Complete Diff**: Review `git diff` to ensure no accidental changes or lockfile corruptions occurred.

---

## 3. Automated Dependency Monitoring (Dependabot)

Dependabot is configured in `.github/dependabot.yml` to perform weekly automated version scans across:
- Python packages (`pip` in `/apps/api`, `/packages/code-intelligence`)
- Node.js packages (`npm` in `/apps/web`)
- Docker base images (`docker` in `/apps/api`, `/apps/web`)
- GitHub Actions workflows (`github-actions` in `/`)

### Invariants for Automated Updates
- Dependabot pull requests **must never be auto-merged**.
- Each PR must pass the complete CI pipeline (Lint, Pytest, Frontend Build).
- Maintainers must verify that no UI/UX styling or business logic was altered by transitive updates.
