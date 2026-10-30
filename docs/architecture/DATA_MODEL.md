# CodeGuard — Relational Data Model & Migration Architecture

**Document ID**: `DOC-ARCH-DATA-01`  
**Application Version**: `1.0.0`  
**Database**: PostgreSQL 16 (Compatible with SQLite 3 for local tests)  
**ORM**: SQLAlchemy 2.0  
**Migration Engine**: Alembic  
**Total Relational Tables**: 27 Domain Tables + 1 Alembic Version Tracking Table  
**Last Verified**: 2026-09-29  

---

## 1. Domain Entity Relationship Diagram

```
[ Organization ] (Tenant Root)
       | 1:N
       +-----------------------+---------------------------------------+
       |                       |                                       |
       v                       v                                       v
[ Repository ]           [ OrgPolicy ]                     [ ToolAudit ] (Immutable)
       | 1:N
       +---------------------------------------+
       |                                       |
       v                                       v
[ PullRequest ]                        [ RepositoryIndex ]
       | 1:N                                   | 1:N
       v                                       +---------------+---------------+
[ ReviewJob ]                                  |               |               |
       |                                       v               v               v
       +-----------------------+          [ CodeSymbol ] [ SymbolRef ] [ FileDep ]
       |                       |
       v 1:N                   v 1:N
  [ AgentRun ]            [ JudgeRun ]
       |                       |
       v 1:N                   v 1:N
  [ AgentTrace ]         [ JudgeDecision ]
       |
       v 1:N
[ ReviewFinding ] <-------------------+
       | 1:N                          |
       +---------------+              |
       |               |              |
       v               v              |
[ FindingEvidence ] [ VerifEvent ]    |
       |                              |
       v                              |
[ ApprovalRequest ]                   |
       | 1:1                          |
       v                              |
[ GitHubPublication ]                 |
       | 1:N                          |
       v                              |
[ GitHubComment ] --------------------+
```

---

## 2. Table Catalog by Alembic Migration Revision

### Revision 001: Initial Core Schema (`001_initial_phase1_tables`)
1. **`organizations`**: Multi-tenant isolation roots holding GitHub App installation bindings, billing status, and plan tiers.
2. **`repositories`**: Monitored source code repositories scoped to an organization with GitHub repository IDs and default branch names.
3. **`pull_requests`**: Ingested PR entities tracking PR number, head SHA, base SHA, author, title, and open/closed state.
4. **`review_jobs`**: Core review lifecycle execution records tracking status (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `STALE`), execution duration, and error logs.
5. **`review_artifacts`**: Raw unified diffs, full-file snapshots, and parsed AST metadata attached to a specific review job.

---

### Revision 002: Code Intelligence Schema (`002_phase2_code_intelligence_tables`)
6. **`repository_indexes`**: Index metadata records for git commits, tracking Tree-sitter AST parsing status and symbol count.
7. **`code_symbols`**: Extracted functions, classes, and methods with byte offsets, line numbers, and docstrings.
8. **`symbol_references`**: Call sites, variable usages, and type annotations linking code symbols across files.
9. **`file_dependencies`**: Cross-file dependency graph edges tracking import statements and module hierarchies.

---

### Revision 003: Multi-Agent AI Review Schema (`003_phase3_agentic_ai_review`)
10. **`agent_runs`**: Execution records for individual AI specialist agents (`security`, `bug`, `performance`, `test`, `contract`, `comprehension`) within a job.
11. **`review_findings`**: Candidate and publishable findings tracking category, severity, file path, line range, message, suggestion, and confidence.
12. **`agent_traces`**: Granular agent execution traces capturing token usage, latency, prompt templates, and raw JSON outputs.

---

### Revision 004: Adversarial Verification Schema (`004_phase4_adversarial_verification`)
13. **`judge_runs`**: Adversarial Judge verification batch executions for a review job.
14. **`judge_decisions`**: Gate-by-gate filtering outcomes (`RETAINED`, `SUPPRESSED`, `DOWNGRADED`) for each candidate finding across the 5 judge gates.
15. **`validation_scenarios`**: Behavioral test scenarios synthesized by the judge to evaluate findings in the sandbox.
16. **`validation_results`**: Output logs and exit codes from execution sandbox tests.
17. **`finding_evidences`**: Citations and AST proofs supporting or refuting a finding.
18. **`verification_events`**: Audit log of verification pipeline state transitions.

---

### Revision 005: Governance, Human Approval & Publishing (`005_phase5_mcp_governance_publishing`)
19. **`approval_requests`**: Human authorization records tracking decision (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `STALE`), authorized user ID, cryptographic signature, and target head SHA.
20. **`tool_execution_audits`**: Immutable, append-only security log recording every tool called by agents or internal services, parameters, risk level, and policy decision.
21. **`organization_review_policies`**: Configurable organization review rules (e.g. require human approval for CRITICAL/HIGH, minimum confidence thresholds).
22. **`github_review_publications`**: Records of reviews published to GitHub, tracking GitHub review ID, composite idempotency key, and publication timestamp.
23. **`github_review_comments`**: Individual inline comments published to GitHub linked to the parent publication and source finding.
24. **`publication_jobs`**: Asynchronous worker tasks executing the atomic GitHub review submission.

---

### Revision 006: Empirical Benchmarking Schema (`006_phase7_benchmarking_tables`)
25. **`benchmark_runs`**: Benchmark evaluation batch runs tracking dataset version, git commit, and execution timestamp.
26. **`benchmark_results`**: Aggregate performance metrics (Precision, Recall, F1, Line Accuracy, Latency percentiles, Total Cost).
27. **`benchmark_finding_evaluations`**: Evaluation comparisons between model-generated findings and ground-truth benchmark labels.

---

## 3. Important Constraints & Composite Indexes

1. **Publication Idempotency Index**:
   ```sql
   CREATE UNIQUE INDEX ix_github_review_publications_unique 
   ON github_review_publications (installation_id, repository_id, head_sha, review_job_id);
   ```
   *Guarantees that re-running a publication job can never create duplicate GitHub reviews on the same commit.*

2. **Tenant Repository Isolation**:
   ```sql
   CREATE UNIQUE INDEX ix_repositories_org_github_id 
   ON repositories (organization_id, github_repo_id);
   ```
   *Guarantees strict tenant boundaries; repositories are strictly owned by a single organization.*

3. **Symbol Deduplication Index**:
   ```sql
   CREATE INDEX ix_code_symbols_file_lines 
   ON code_symbols (repository_index_id, file_path, line_start, line_end);
   ```
   *Accelerates AST enclosing-entity lookups during diff hunk processing.*

---

## 4. State Machines & Lifecycle Transitions

### 4.1 Review Job Lifecycle (`ReviewJobStatus`)
```
[ PENDING ] ──(Worker picks up)──> [ RUNNING ] ──(Pipeline success)──> [ COMPLETED ]
      │                                 │
      │                                 └──(Unhandled exception)────> [ FAILED ]
      │
      └──(PR Head SHA moved)─────────────────────────────────────────> [ STALE ]
```

### 4.2 Review Finding Lifecycle (`FindingStatus`)
```
[ CANDIDATE ] ──(Specialist generates finding)
      │
      ├──(Judge Gate 1-3 reject)───────────> [ SUPPRESSED ]
      │
      └──(Judge approves)─────────────────> [ VERIFIED ]
                                                 │
            ┌────────────────────────────────────┴────────────────────────────────────┐
            ▼ (Consequential tool policy)                                             ▼ (Read-only / Low-risk)
     [ PENDING_APPROVAL ]                                                      [ APPROVED ]
            │                                                                         │
            ├──(Operator rejects)──────────> [ REJECTED ]                             │
            │                                                                         │
            └──(Operator approves)─────────> [ APPROVED ] ──(Publisher posts)────────> [ PUBLISHED ]
```

### 4.3 Human Approval Request Lifecycle (`ApprovalStatus`)
```
[ PENDING ] ──(Operator approves)──> [ APPROVED ] ──(Commit drift detected)──> [ STALE ]
     │
     ├──(Operator rejects)─────────> [ REJECTED ]
     │
     └──(Timeout exceeded)─────────> [ EXPIRED ]
```

---

## 5. Migration Workflow & Database Management

CodeGuard enforces the **Expand-and-Contract Migration Pattern** to allow zero-downtime rolling updates.

### 5.1 Standard Migration Commands
```bash
# 1. Apply all pending migrations to HEAD
alembic -c apps/api/alembic.ini upgrade head

# 2. Inspect current applied revision
alembic -c apps/api/alembic.ini current

# 3. View migration history
alembic -c apps/api/alembic.ini history --verbose

# 4. Rollback single migration step
alembic -c apps/api/alembic.ini downgrade -1
```

### 5.2 Backup & Restoration
- **Automated Backup**: `python scripts/backup_db.py --output-dir ./backups` produces gzip-compressed, SHA-256 verified database snapshots.
- **Automated Restore**: `python scripts/restore_db.py --backup-file ./backups/<file>.gz --confirm-restore` validates table count (27 domain tables) and schema consistency upon restoration.
