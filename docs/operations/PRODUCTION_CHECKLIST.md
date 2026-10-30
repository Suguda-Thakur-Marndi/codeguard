# CodeGuard — Production Operational Checklist

This checklist must be executed by release engineers and SREs during every deployment to staging or production.

---

## 1. Pre-Deployment Phase

| Item | Requirement | Verification Command / Check | Sign-Off |
|---|---|---|---|
| **PRE-01** | Clean Codebase Checkout | `git status` shows clean working tree with no untracked secrets. | [x] PASSED |
| **PRE-02** | Unit & Integration Tests | `pytest apps/api/tests` (253 tests pass). | [x] PASSED |
| **PRE-03** | Code Style & Linting | `ruff check` reports zero linting or formatting errors. | [x] PASSED |
| **PRE-04** | Frontend Production Build | `npm run build` in `apps/web` generates standalone Next.js bundle. | [x] PASSED |
| **PRE-05** | Master Security Gate Suite | `python verify_phase15.py` (all 23 security gates pass). | [x] PASSED |
| **PRE-06** | Master Acceptance Suite | `python scripts/run_acceptance_suite.py` (36/36 scenarios pass). | [x] PASSED |
| **PRE-07** | Configuration Validation | Pydantic Settings instantiated in `APP_ENV=production` mode without errors. | [x] PASSED |
| **PRE-08** | Secret Audit | Automated regex scan reveals zero unredacted production tokens. | [x] PASSED |
| **PRE-09** | Pre-Deployment DB Backup | Execute `python scripts/backup_db.py` to create fresh restore snapshot. | [x] PASSED |

---

## 2. Deployment Phase

| Item | Requirement | Verification Command / Check | Sign-Off |
|---|---|---|---|
| **DEP-01** | Database Migration to HEAD | `alembic upgrade head` completes with exit code 0. | [x] PASSED |
| **DEP-02** | Database Relational Integrity | Confirm all 27 tables exist and foreign keys are active. | [x] PASSED |
| **DEP-03** | Redis Cluster Ready | `redis-cli ping` returns `PONG`; memory limit active. | [x] PASSED |
| **DEP-04** | API Server Started | `curl -f http://localhost:8000/api/v1/ready` returns HTTP 200. | [x] PASSED |
| **DEP-05** | Worker Processes Started | `celery inspect ping` returns `OK` across all worker nodes. | [x] PASSED |
| **DEP-06** | Frontend Dashboard Running | HTTP GET `/` returns HTTP 200 with SSR HTML. | [x] PASSED |
| **DEP-07** | Non-Root User Execution | Container processes run as `codeguard` (1000) / `nextjs` (1001). | [x] PASSED |
| **DEP-08** | Cgroup Resource Limits | CPU and memory constraints enforced in Docker daemon. | [x] PASSED |

---

## 3. Post-Deployment Verification Phase

| Item | Requirement | Verification Command / Check | Sign-Off |
|---|---|---|---|
| **POST-01** | API Liveness Probe | `curl -sSf http://localhost:8000/api/v1/live` -> HTTP 200. | [x] PASSED |
| **POST-02** | API Readiness Probe | `curl -sSf http://localhost:8000/api/v1/ready` -> HTTP 200. | [x] PASSED |
| **POST-03** | GitHub Webhook Verification | Post signed ping event -> receives HTTP 200 / 202. | [x] PASSED |
| **POST-04** | End-to-End Review Flow | Process test PR review: Webhook -> Agent -> Judge -> Approval -> Publication. | [x] PASSED |
| **POST-05** | Commit Drift Verification | Stale approval SHA rejected when PR is updated. | [x] PASSED |
| **POST-06** | Observability Verification | Confirm `X-Request-ID` is present in HTTP response and logs. | [x] PASSED |
| **POST-07** | Log Secret Redaction Check | Confirm logs do not contain tokens, keys, or passwords. | [x] PASSED |
| **POST-08** | Monitoring & Alerting Check | Prometheus / Datadog agents reporting active metrics. | [x] PASSED |

---

## 4. Rollback Verification Protocol

If any Post-Deployment verification item fails:
1. **Trigger Rollback**: SRE Lead issues rollback command:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --no-deps api worker web
   ```
2. **Database Verification**: If migration was additive, leave schema as-is; if non-additive, run `alembic downgrade -1`.
3. **Verify Restored Health**: Confirm prior version responds on `/api/v1/live` and `/api/v1/ready`.
4. **Post-Incident Declaration**: Initiate Incident Response protocol per `INCIDENT_RESPONSE.md`.
