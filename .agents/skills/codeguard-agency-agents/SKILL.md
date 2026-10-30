---
name: codeguard-agency-agents
description: >-
  Specialized engineering roles and execution contracts for CodeGuard development.
  Covers the 12 domain agents: Architect, Backend, Frontend, Database, Security,
  Policy & Governance, AI/LangGraph, Code Intelligence, Testing, DevOps, Review, and Final Integration.
---

# CodeGuard Agency Agents

This skill governs the responsibilities, input/output schemas, and execution boundaries of the 12 specialized engineering agents.

## Role Matrix & File Ownership

| Agent Role | Primary Ownership | Core Responsibilities | Disallowed Actions |
| :--- | :--- | :--- | :--- |
| **Architect** | High-level system & boundaries | Module boundaries, minimal change proposals, architecture compliance | Redesigning architecture, writing broad ad-hoc changes |
| **Backend** | `apps/api/` | FastAPI routers, business services, authentication, workers | Breaking API contracts, inventing duplicate services |
| **Frontend** | `apps/web/` | Next.js components, API hooks, client state, error boundaries | Redesigning UI/UX, altering layouts/colors |
| **Database** | `apps/api/alembic/`, models | PostgreSQL schemas, migrations, indexes, constraints | Direct DB mutations, bypassing Alembic, dropping tables |
| **Security** | Security boundary | Zero-trust verification, auth/authz review, prompt injection, sandbox | Bypassing auth, hardcoding secrets, approving untrusted inputs |
| **Policy & Governance** | `apps/api/app/core/policy.py`, policy schemas | Tool schemas, zero-trust policy, audit logging, approval integration | Bypassing policy checks, auto-executing dangerous tools |
| **AI / LangGraph** | `apps/api/app/agents/` | Gemini routing, LangGraph graph, prompt templates, structured output | Treating AI as authority, bypassing Adversarial Judge |
| **Code Intelligence**| `packages/code-intelligence/`| Tree-sitter parsers, AST mappings, diff indexer, dependency graph | Replacing Tree-sitter with regex, weakening parser diagnostics |
| **Testing** | `apps/api/tests/` | Unit, integration, security, benchmark regression tests | Weakening tests, deleting failing assertions |
| **DevOps** | `docker/`, `infra/`, root configs| Docker, compose manifests, environment variables, health checks | Committing secrets, unnecessary cloud alterations |
| **Review** | Pull requests & diffs | Independent quality, correctness, security, maintainability gate | Approving without verification, rubber-stamping |
| **Final Integration**| Cross-cutting | Multi-service verification, import validation, end-to-end flow | Overriding specialist findings, skipping test runs |

## Standard Agent Output Format

Every agent must format its findings and implementation report as follows:

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
