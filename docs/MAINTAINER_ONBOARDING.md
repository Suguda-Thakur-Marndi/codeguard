# CodeGuard — Maintainer Onboarding & Knowledge Transfer Checklist

**Document ID**: `DOC-ONBOARD-01`  
**Application Version**: `1.0.0`  
**Intended Audience**: New Core Maintainers, SREs, and Platform Engineers  
**Last Verified**: 2026-09-29  

---

## 1. Onboarding Mission & Scope

Welcome to the CodeGuard engineering team. This document provides an actionable, 12-step onboarding protocol designed to enable a new competent engineer to understand, run, verify, and maintain the system independently.

Every checklist item below is linked to empirical documentation and reproduction commands.

---

## 2. The 12-Step Maintainer Onboarding Checklist

### [x] Step 1: Obtain Authorized Repository Access & Verify Integrity
- **Action**: Clone the official repository and inspect git commit history and signature validity.
  ```bash
  git clone https://github.com/Suguda-Thakur-Marndi/codeguard-ai.git
  cd codeguard-ai
  git status
  ```
- **Verification Evidence**: Working tree clean on branch `main` at commit `085615e` / `e917495`.
- **Reference**: [`README.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/README.md).

---

### [x] Step 2: Review Project Overview & Prime Directives
- **Action**: Read the core system architecture, Prime Directive, and multi-agent engineering rules.
- **Key Rules to Absorb**:
  1. *Tools are assistants, not authorities*: Deterministic backend and database logic override LLM reasoning.
  2. *No UI/UX redesigns*: Frontend styling and components in `apps/web/` are preserved invariants.
  3. *Zero-weaken test policy*: If a test fails, fix the code; never delete or loosen assertions.
- **Reference**: [`AGENTS.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/AGENTS.md), [`GEMINI.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/GEMINI.md).

---

### [x] Step 3: Set Up the Local Development Environment
- **Action**: Create an isolated Python 3.11+ virtual environment and install monorepo packages in editable mode.
  ```bash
  python -m venv .venv
  # Windows: .\.venv\Scripts\Activate.ps1 | Linux: source .venv/bin/activate
  pip install -e "./packages/code-intelligence" -e "./apps/api[dev]"
  cd apps/web && npm install && cd ../..
  ```
- **Verification Evidence**: Packages `codeguard-api` and `codeguard-code-intelligence` visible in `pip list`.
- **Reference**: [`docs/SETUP.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/SETUP.md).

---

### [x] Step 4: Configure Local Services & Environment Variables
- **Action**: Copy the environment template and verify configuration settings.
  ```bash
  cp .env.example .env
  ```
- **Important Settings**: Ensure `APP_ENV=development` and `DEV_AUTH_BYPASS=true` for local development. Verify that `CELERY_TASK_ALWAYS_EAGER=true` if running without an active Redis daemon.
- **Reference**: [`docs/SETUP.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/SETUP.md) Section 3.

---

### [x] Step 5: Initialize the Database & Verify Migrations
- **Action**: Run Alembic migrations to apply all 27 domain tables.
  ```bash
  alembic -c apps/api/alembic.ini upgrade head
  alembic -c apps/api/alembic.ini current
  ```
- **Verification Evidence**: Alembic reports revision `006_phase7_benchmarking_tables (head)`.
- **Reference**: [`docs/architecture/DATA_MODEL.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/architecture/DATA_MODEL.md).

---

### [x] Step 6: Start Application Services Locally
- **Action**: Start the FastAPI backend server on port 8000.
  ```powershell
  .\.venv\Scripts\uvicorn app.main:app --app-dir apps/api --port 8000
  ```
- **Verification Evidence**:
  - `curl http://localhost:8000/api/v1/live` $\rightarrow$ `{"status": "ok"}`
  - `curl http://localhost:8000/api/v1/ready` $\rightarrow$ `{"status": "ok", "database": true}`
- **Reference**: [`docs/SETUP.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/SETUP.md) Section 5.

---

### [x] Step 7: Run the Test Suites
- **Action**: Execute all unit tests, acceptance scenarios, and linter gates.
  ```powershell
  # 1. Run all backend unit, security & integration tests
  .\.venv\Scripts\python.exe -m pytest apps/api/tests -q
  # 2. Run Ruff linter
  .\.venv\Scripts\ruff.exe check .
  # 3. Run Frontend typecheck & production build
  cd apps/web; npm run lint; npm run build; cd ../..
  ```
- **Verification Evidence**: 232/232 pytest tests pass; Ruff reports `All checks passed!`; Next.js compiles 16 static/dynamic routes with 0 errors.
- **Reference**: [`docs/TESTING.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/TESTING.md).

---

### [x] Step 8: Trace One Pull Request Review Request
- **Action**: Follow a simulated review lifecycle from webhook ingestion to finding generation.
- **Trace Walkthrough**:
  1. Ingress webhook received at `/api/v1/webhooks/github` with valid HMAC signature.
  2. Webhook service drops replays and enqueues task in Celery worker.
  3. Tree-sitter extracts diff hunks and enclosing AST entities.
  4. LangGraph StateGraph invokes Comprehension, routes to Security/Bug specialists.
  5. Adversarial Judge filters candidate findings across the 5 gates.
- **Reference**: [`docs/architecture/AGENT_AND_REVIEW_FLOW.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/architecture/AGENT_AND_REVIEW_FLOW.md).

---

### [x] Step 9: Understand Approval & Publishing Boundaries
- **Action**: Review how human authorization gates prevent unverified AI reviews from publishing to GitHub.
- **Key Concepts**:
  - Consequential actions require cryptographically signed approval from a `REVIEWER` or `ADMIN`.
  - Stale approval protection: If the PR head SHA moves, existing approvals are invalidated (`COMMIT_DRIFT`).
- **Reference**: [`docs/architecture/AGENT_AND_REVIEW_FLOW.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/architecture/AGENT_AND_REVIEW_FLOW.md) Section 6.

---

### [x] Step 10: Review Security Invariants & Incident Response Procedures
- **Action**: Familiarize yourself with zero-trust boundaries, emergency kill-switches, and secret rotation playbooks.
- **Key Actions**:
  - Emergency review disablement: Set `auto_publish_enabled=false` in organization policy.
  - Secret rotation: Follow documented procedures in Section 5 of the Runbook.
- **Reference**: [`docs/RUNBOOK.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/RUNBOOK.md), [`docs/SECURITY_RUNBOOK.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/SECURITY_RUNBOOK.md), [`docs/security/THREAT_MODEL.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/security/THREAT_MODEL.md).

---

### [x] Step 11: Understand Deployment, Scaling & Rollback
- **Action**: Review Docker Compose production orchestration and Alembic schema rollback commands.
- **Key Commands**:
  - Deploy stack: `docker compose -f docker-compose.prod.yml up -d --build`
  - Rollback code: `git checkout v1.0.0-stable && docker compose -f docker-compose.prod.yml up -d --build`
  - Rollback DB: `alembic -c apps/api/alembic.ini downgrade -1`
- **Reference**: [`docs/RUNBOOK.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/RUNBOOK.md) Section 7.

---

### [x] Step 12: Review Known Limitations & Next Action Register
- **Action**: Inspect the current known limitations and prioritized tasks for future releases.
- **Current Limitations**:
  - Release state is currently **MORE EVIDENCE REQUIRED** pending an authorized customer pilot.
  - General availability release to production requires explicit Project Owner approval.
- **Reference**: [`docs/operations/DEPLOYMENT.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/operations/DEPLOYMENT.md).
