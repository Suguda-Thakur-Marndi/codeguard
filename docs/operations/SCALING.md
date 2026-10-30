# CodeGuard — Horizontal & Vertical Scaling Architecture

This document defines the scaling model, concurrency controls, database connection pool sizing, and backpressure mechanisms for CodeGuard.

---

## 1. Scaling Topology Overview

CodeGuard separates synchronous I/O from heavy computational and AI workflows, allowing independent scaling of web, API, and worker nodes:

```
                          [Load Balancer]
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       [API Instance 1]                 [API Instance 2]
         (4 Workers)                      (4 Workers)
                 │                               │
                 └───────────────┬───────────────┘
                                 │
                   ┌─────────────┴─────────────┐
                   ▼                           ▼
            [PostgreSQL 16]              [Redis 7 Cluster]
            (Connection Pool)            (Task Queue Broker)
                                               │
                                 ┌─────────────┴─────────────┐
                                 ▼                           ▼
                        [Worker Instance 1]         [Worker Instance 2]
                          (Concurrency: 4)            (Concurrency: 4)
```

---

## 2. Worker Scaling & Concurrency Model

The review pipeline is executed by Celery workers subscribing to the `celery` queue in Redis.

### Worker Sizing & Configuration
- **Process Model**: Multi-process worker pool (`celery worker -P prefork`).
- **Default Concurrency**: 4 worker processes per container (`--concurrency=4`).
- **Fair Dispatch**: `task_acks_late=True` and `prefetch_multiplier=1`.
  - *Rationale*: Long-running LLM review jobs (1-5s) must not be hoarded by a single worker process; tasks are distributed fairly across all available workers.

### Horizontal Worker Scaling
To scale worker capacity under heavy PR traffic bursts:
```bash
# Scale to 4 worker container replicas (16 concurrent review tasks)
docker compose -f docker-compose.prod.yml up -d --scale worker=4
```

---

## 3. Database Connection Pool Sizing

Database connections must be carefully managed to prevent connection exhaustion in PostgreSQL:

### Pool Calculation Formula
Total database connections demanded across the cluster:
$$\text{Total Connections} = (\text{API Replicas} \times \text{Uvicorn Workers} \times \text{DB\_POOL\_SIZE}) + (\text{Worker Replicas} \times \text{Worker Concurrency} \times \text{DB\_POOL\_SIZE})$$

### Production Settings
- `DB_POOL_SIZE`: 20 (base pool)
- `DB_MAX_OVERFLOW`: 40 (burst pool)
- `DB_POOL_TIMEOUT`: 30 seconds
- **PostgreSQL `max_connections`**: Set to `200` minimum in `postgresql.conf`.

---

## 4. Resource Boundaries & Backpressure Protection

To protect the infrastructure and Gemini AI quotas from unbounded resource consumption during massive PRs or denial-of-service attempts, CodeGuard enforces hard boundaries:

| Resource Constraint | Boundary Limit | Enforcement Point | Behavior on Breach |
|---|---|---|---|
| **Max PR Diff Lines** | 5,000 lines | Diff Parser | Truncates diff to top modified files; logs informational notice. |
| **Max Context Characters** | 16,000 chars | Agent Context Ranker | Safely drops lowest-ranked AST symbols to fit context window. |
| **Max Context Files** | 10 files | File Filter | Prioritizes files with highest risk change density. |
| **Max Context Symbols** | 30 symbols | Semantic Indexer | Limits reference graph expansion depth. |
| **Specialist LLM Concurrency** | 4 parallel calls | LangGraph Orchestrator | Throttles specialist agents to avoid Gemini 429 quota exhaustion. |
| **LLM Request Retries** | 2 retries | LLM Client | Exponential backoff (1s, 2s); terminates with controlled error on exhaustion. |
| **Execution Sandbox CPU** | 1.0 CPU core | Docker Sandbox | Hard cgroup CPU limit. |
| **Execution Sandbox Memory** | 512 MB | Docker Sandbox | OOM-killer terminates runaway sandbox sub-process safely. |
| **Execution Sandbox Timeout** | 30 seconds | Sandbox Runner | Kills validation command (pytest/ruff) if hanging. |
| **HTTP Request Body Size** | 25 MB | Reverse Proxy & API | Rejects with HTTP 413 Payload Too Large. |
