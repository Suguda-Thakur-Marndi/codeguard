# CodeGuard — Release Engineering & Deployment Process

This document defines the official release lifecycle, semantic versioning policy, release gates, and deployment protocols for CodeGuard.

---

## 1. Release Strategy & Semantic Versioning

CodeGuard follows **Semantic Versioning 2.0.0** (`vMAJOR.MINOR.PATCH`):
- **MAJOR**: Breaking API schema changes, fundamental architectural shifts, or backward-incompatible database migrations.
- **MINOR**: New specialized agents, safe tool integrations, or operational feature enhancements.
- **PATCH**: Bug fixes, security patches, performance tuning, or documentation updates.

### Release Artifact Tags
- Git Tag: `v1.0.0-release`
- Docker Images: `codeguard/api:1.0.0`, `codeguard/worker:1.0.0`, `codeguard/web:1.0.0`
- Companion SHA: Exact git commit hash recorded in build metadata.

---

## 2. Mandatory Production Release Gates

Before any production release can be approved or deployed, all **27 Release Gates** must pass with deterministic evidence:

| Gate | Verification Scope | Verification Method | Status |
|---|---|---|---|
| **GATE 1** | Clean Build | `npm run build` in web, Python packages install cleanly | **PASS** |
| **GATE 2** | Configuration Validation | Pydantic Settings fail-fast validation against invalid/missing configs | **PASS** |
| **GATE 3** | Secret Protection | Zero unredacted secrets in git history or active source files | **PASS** |
| **GATE 4** | Database Migrations | Alembic upgrade to HEAD succeeds on empty database | **PASS** |
| **GATE 5** | Database Backup & Restore | `scripts/backup_db.py` & `scripts/restore_db.py` drill with SHA-256 verification | **PASS** |
| **GATE 6** | Redis Broker & Cache | Connectivity and degradation fallback verified | **PASS** |
| **GATE 7** | Worker Crash Recovery | Worker interrupt and restart leaves jobs in consistent state | **PASS** |
| **GATE 8** | GitHub Webhook Security | HMAC-SHA256 constant-time verification & replay protection | **PASS** |
| **GATE 9** | Gemini Provider Routing | Fast and reasoning model tiers routed with token pricing calculations | **PASS** |
| **GATE 10** | Zero-Trust Policy Engine | PolicyEngine blocks dangerous actions, schemas strictly enforced | **PASS** |
| **GATE 11** | Human Approval Gate | Consequential operations require valid human approval record | **PASS** |
| **GATE 12** | Stale Approval Block | Commit drift (changed head SHA) invalidates approval | **PASS** |
| **GATE 13** | GitHub Publication Safety | Out-of-hunk line numbers rejected; valid comments posted | **PASS** |
| **GATE 14** | Duplicate Publication Guard | Idempotency composite key prevents double-commenting | **PASS** |
| **GATE 15** | Authentication Enforcement | JWT verification, expiration, and production bypass block | **PASS** |
| **GATE 16** | Server-Side Authorization | RBAC (MEMBER, REVIEWER, ADMIN) enforced at endpoint handlers | **PASS** |
| **GATE 17** | Multi-Tenant Isolation | Cross-tenant database queries, approvals, and jobs blocked | **PASS** |
| **GATE 18** | Prompt Injection Defense | Injection payloads in diffs/comments cannot hijack execution | **PASS** |
| **GATE 19** | Distributed Observability | `X-Request-ID` causal correlation trace through full review lifecycle | **PASS** |
| **GATE 20** | Failure Recovery | System recovers gracefully from transient service outages | **PASS** |
| **GATE 21** | Rollback Compatibility | Additive migrations verified; rollback procedure documented | **PASS** |
| **GATE 22** | Performance Baseline | Probes < 15ms, AST diff parse < 30ms, full review < 3500ms | **PASS** |
| **GATE 23** | Cost Controls | Context size caps, model pricing, and retry bounds active | **PASS** |
| **GATE 24** | Master Security Suite | All 23 security gates pass (`verify_phase15.py`) | **PASS** |
| **GATE 25** | Master Acceptance Suite | All 30 acceptance scenarios & 6 audits pass (`run_acceptance_suite.py`) | **PASS** |
| **GATE 26** | Master Regression Suite | Zero performance or functional regressions (`test_regression_suite.py`) | **PASS** |
| **GATE 27** | Clean Checkout Validation | Working tree clean, zero unstaged secrets or debug code | **PASS** |

---

## 3. Production Deployment Step-by-Step Workflow

```
[1. Pre-Flight] Run Security & Acceptance Suites
      │
      ▼
[2. Tag Release] git tag -a v1.0.0-release -m "CodeGuard Release v1.0.0"
      │
      ▼
[3. Build Images] docker compose -f docker-compose.prod.yml build
      │
      ▼
[4. Staging Deploy] Deploy to staging cluster & execute smoke test
      │
      ▼
[5. Staging Sign-Off] Confirm all 27 Release Gates pass in staging
      │
      ▼
[6. Database Backup] Execute pre-deployment snapshot: python scripts/backup_db.py
      │
      ▼
[7. DB Migration] docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
      │
      ▼
[8. Production Deploy] docker compose -f docker-compose.prod.yml up -d
      │
      ▼
[9. Post-Deploy Verification] Verify /api/v1/live, /api/v1/ready, /health, and dashboard
```

---

## 4. Emergency Hotfix Procedure

When a critical vulnerability or operational defect is discovered in production:
1. Branch from release tag: `git checkout -b hotfix/v1.0.1 v1.0.0-release`.
2. Apply minimal targeted fix.
3. Write a permanent regression test in `apps/api/tests/`.
4. Run security and regression suites:
   ```bash
   pytest apps/api/tests/test_regression_suite.py apps/api/tests/test_security_audit_phase15.py
   ```
5. Tag hotfix: `git tag -a v1.0.1-release -m "Hotfix: resolve issue XYZ"`.
6. Deploy hotfix image to production following the standard deployment checklist.
