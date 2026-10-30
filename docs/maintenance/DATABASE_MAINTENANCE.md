# CodeGuard — Database Maintenance & Schema Evolution Guide

## 1. Database Architecture & Schema Baseline

CodeGuard uses PostgreSQL 16 (production/staging) and SQLite (hermetic local testing/isolated test runners). The schema is managed strictly via Alembic migrations located in `apps/api/alembic/versions/`.

### 1.1 Migration Revision History

| Revision ID | Description | Core Tables Introduced | Downgrade Tested |
| :--- | :--- | :--- | :--- |
| `001_initial_phase1_tables` | Core multi-tenant and GitHub repository models | `organizations`, `repositories`, `pull_requests`, `review_jobs` | Yes |
| `002_phase2_code_intelligence_tables` | AST, symbol tables, reference graphs, call graphs | `ast_nodes`, `symbols`, `references`, `call_graph_edges`, `diff_hunks` | Yes |
| `003_phase3_agentic_ai_review` | Multi-agent findings, raw observations, agent traces | `agent_runs`, `review_findings`, `finding_locations`, `evidence_items` | Yes |
| `004_phase4_adversarial_verification` | Adversarial judge verdicts, test executions, sandbox runs | `judge_evaluations`, `verification_results`, `sandbox_runs`, `rejection_logs` | Yes |
| `005_phase5_mcp_governance_publishing` | Zero-trust policies, human approvals, audit logs, publications | `governance_policies`, `approval_requests`, `approval_signatures`, `tool_execution_audits`, `github_review_publications` | Yes |
| `006_phase7_benchmarking_tables` | Empirical benchmark runs, ground-truth scenarios, metrics | `benchmark_runs`, `benchmark_scenarios`, `benchmark_metrics` | Yes |

Total tracked domain tables: **27 tables**.

---

## 2. Zero-Downtime Migration Pattern: Expand-and-Contract

All production schema modifications must follow the **Expand-and-Contract** pattern to prevent table locks and application downtime during rolling deployments.

```text
PHASE 1: EXPAND (Backward Compatible)
- Add new nullable columns or tables.
- Add new indexes concurrently.
- Deploy updated application code writing to BOTH old and new columns.

PHASE 2: BACKFILL (Data Migration)
- Run idempotent background job backfilling data from old to new columns in batches.

PHASE 3: CONTRACT (Cleanup)
- Deploy application code reading and writing ONLY to new columns.
- Drop obsolete columns or tables in a subsequent migration.
```

### Invariants for Migrations
- **No Direct Table Rewrites**: Never run `ALTER TABLE ... ALTER COLUMN ... TYPE` on high-volume tables (`review_findings`, `audit_logs`) without an intermediate column.
- **Concurrent Indexes in PostgreSQL**: In PostgreSQL migrations, indexes must be created with `CONCURRENTLY` to avoid blocking writes:
  ```sql
  CREATE INDEX CONCURRENTLY idx_review_findings_repo ON review_findings (repository_id, created_at);
  ```
- **Reversible Migrations**: Every `upgrade()` function must have an accompanying, tested `downgrade()` function.

---

## 3. Connection Pool Configuration & Tuning

Database connections are managed via SQLAlchemy's `QueuePool`. Settings are defined in `app.core.config.Settings`:

| Parameter | Recommended Dev | Staging | Production | Description |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_POOL_SIZE` | 5 | 10 | 25 | Persistent open connections per worker process |
| `DATABASE_MAX_OVERFLOW` | 10 | 20 | 50 | Temporary surge connections during traffic spikes |
| `DATABASE_POOL_TIMEOUT` | 30s | 30s | 15s | Seconds to wait before throwing `TimeoutError` |
| `DATABASE_POOL_RECYCLE` | 1800s | 1800s | 1800s | Connection lifetime before recycling (prevents stale TCP) |

### Pool Exhaustion Remediation
If connection timeout errors occur (`QueuePool limit of size 25 overflow 50 reached`):
1. Check for long-running uncommitted transactions or orphaned sessions.
2. Ensure async database sessions are always wrapped in context managers (`async with get_db() as session:`).
3. Scale out read queries to a read-replica pool.

---

## 4. Data Retention, Archival & Privacy Policy

To protect intellectual property, prevent database bloat, and comply with enterprise data governance:

| Data Type | Retention Window | Storage Tier | Archival / Cleanup Procedure |
| :--- | :--- | :--- | :--- |
| **Source Code Diffs** | 30 Days | Hot DB (`diff_hunks`) | Automated truncation after PR review completion |
| **Raw LLM Agent Traces** | 14 Days | Hot DB (`agent_runs`) | Compressed to JSON archive in cold storage or pruned |
| **Verified Findings** | 1 Year | Hot DB (`review_findings`)| Retained for audit and security tracking |
| **Tool & Policy Audit Logs** | 3 Years | Append-only DB (`audit_logs`) | Exported to immutable WORM storage monthly |
| **Human Approval Signatures** | 3 Years | Hot DB (`approval_signatures`)| Tamper-evident hash chain preserved |
| **Benchmark Artifacts** | Permanent | File/DB (`benchmark_runs`) | Anonymized synthetic data only; no customer code |

### Sensitive Data Scrubbing
- **No Private Source Code in Evaluation Artifacts**: Benchmarks and test reports must only use synthetic fixtures from `evaluation/datasets/` or `fixtures/`.
- **API Secret Scrubbing**: All request headers, webhooks, and log outputs are filtered through `app.core.security.mask_secret` prior to persistence.

---

## 5. Backup Verification & Disaster Recovery

- **Automated Daily Snapshots**: Full PostgreSQL physical database dump created daily at 02:00 UTC using `pg_dump -Fc`.
- **Continuous WAL Archiving**: Point-in-time recovery (PITR) enabled via continuous write-ahead log shipping to encrypted object storage.
- **Weekly Restoration Drill**: Every Sunday, an automated cron job restores the latest snapshot into an isolated staging database and executes `python verify_phase16.py` to confirm zero data corruption.
- **Recovery Time Objective (RTO)**: < 30 minutes.
- **Recovery Point Objective (RPO)**: < 5 minutes.
