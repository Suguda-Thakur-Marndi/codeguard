# CodeGuard — Dependency Inventory & Ecosystem Map

**Document Status**: Active / Authoritative  
**Date**: September 17, 2026  
**Auditor**: Continuous Engineering & DevOps Team

---

## 1. Monorepo Dependency Overview

CodeGuard strictly segregates dependencies across specialized micro-packages and application services:
1. `apps/api`: Production backend, API endpoints, LangGraph orchestrator, database ORM, and Celery workers.
2. `packages/code-intelligence`: Core AST parsers, unified diff indexers, and dependency graph engines.
3. `apps/web`: Next.js 15 App Router web client.

---

## 2. Python Ecosystem Dependencies (`apps/api`)

| Package Name | Constraint / Version | Purpose | Security & Upgrade Notes |
| :--- | :--- | :--- | :--- |
| `fastapi` | `>=0.111.0` | Asynchronous REST API framework | High stability. Enforces strict OpenAPI 3.1 contracts. |
| `uvicorn[standard]` | `>=0.30.0` | High-performance ASGI production server | Standard loop and HTTP protocol handlers. |
| `pydantic` | `>=2.7.0` | Type validation, serialization, and settings | Core data validation contract across all agents. |
| `pydantic-settings`| `>=2.3.0` | Environment configuration loading | Enforces zero-unassigned settings at boot. |
| `sqlalchemy` | `>=2.0.30` | 2.0-style Type-annotated SQL ORM | Enforces foreign key constraints and connection pooling. |
| `alembic` | `>=1.13.1` | Relational database schema migration runner | Manages 6 migration revisions and 27 tables. |
| `psycopg2-binary` | `>=2.9.9` | PostgreSQL database adapter | Production PostgreSQL connection engine. |
| `redis` | `>=5.0.4` | In-memory cache and task queue broker | Supports graceful degradation when offline in staging. |
| `celery` | `>=5.4.0` | Distributed asynchronous task queue | Worker concurrency, task acks, and dead-letter queues. |
| `httpx` | `>=0.27.0` | Async HTTP client for external integrations | GitHub API calls, webhook dispatch, and timeouts. |
| `cryptography` | `>=42.0.7` | Cryptographic primitives & HMAC | Webhook HMAC-SHA256 constant-time verification. |
| `pyjwt[crypto]` | `>=2.8.0` | JWT authentication and tenant isolation | Token generation and cryptographic signing. |
| `tree-sitter` | `>=0.24.0` | Incremental AST parsing engine | High-performance native C-bindings. |
| `tree-sitter-python`| `>=0.25.0`| Python grammar grammar for tree-sitter | Deterministic AST chunking for Python sources. |
| `tree-sitter-javascript`|`>=0.25.0`| JavaScript grammar for tree-sitter | Deterministic AST chunking for JS sources. |
| `tree-sitter-typescript`|`>=0.23.0`| TypeScript grammar for tree-sitter | Deterministic AST chunking for TS/TSX sources. |
| `unidiff` | `>=1.0.0` | Unified diff parsing library | Git diff hunk and line parsing. |
| `langgraph` | `>=0.2.0` | State graph multi-agent orchestration | Cyclical graph execution with checkpointing. |
| `google-genai` | `>=0.1.0` | Official Google GenAI SDK | AI specialist and judge reasoning runtime. |

### Development & Test Dependencies (`apps/api[dev]`)
| Package Name | Version | Purpose |
| :--- | :--- | :--- |
| `pytest` | `>=8.2.1` | Master test runner |
| `pytest-asyncio` | `>=0.23.7` | Asynchronous test loop management (`Mode.AUTO`) |
| `pytest-mock` | `>=3.14.0` | Mocking engine for GitHub REST and external LLMs |
| `fakeredis` | `>=2.23.2` | In-memory Redis simulation for offline test execution |
| `ruff` | `>=0.4.5` | Fast Python linter and formatter |
| `mypy` | `>=1.10.0` | Static type analysis |

---

## 3. Frontend Ecosystem Dependencies (`apps/web`)

| Package Name | Version | Purpose |
| :--- | :--- | :--- |
| `next` | `^15.2.0` | React server-side rendering and static export framework |
| `react` | `^19.0.0` | UI component library |
| `react-dom` | `^19.0.0` | React DOM renderer |
| `tailwindcss` | `^3.4.17` | Utility-first CSS styling engine |
| `lucide-react` | `^1.16.0` | Accessible icon library |
| `clsx` | `^2.1.1` | Conditional className composer |
| `tailwind-merge` | `^3.0.2` | Conflict-free Tailwind class resolution |
| `typescript` | `^5.8.2` | Strict JavaScript type system |

---

## 4. Upgrade & Version Safety Policy

1. **Context7 Protocol**: Prior to any dependency upgrade, verify target library versions against installed locks and consult official release changelogs.
2. **Deterministic Version Pinning**:
   - Monorepo packages use lower-bound constraints (`>=X.Y.Z`) in library definitions and exact pins in runtime virtual environments (`.venv`).
   - Frontend locks are strictly committed in `package-lock.json` and deployed via `npm ci`.
3. **No Breaking Upgrades**: Upgrades that modify public APIs or break backwards-compatibility with existing stored database models are strictly rejected.
