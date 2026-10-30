# CodeGuard — Observability & Monitoring Guide

This guide establishes the monitoring architecture, structured logging formats, distributed correlation tracing, and telemetry metrics implemented in CodeGuard.

---

## 1. Structured JSON Logging Format

All application services emit single-line, structured JSON logs to standard output (`stdout`), formatted for ingestion by log collectors (Fluentbit, Vector, CloudWatch, Datadog):

```json
{
  "timestamp": "2026-09-18T13:30:02.941477+00:00",
  "level": "INFO",
  "logger": "codeguard",
  "message": "HTTP POST /api/v1/webhooks/github -> 202 in 14.20ms",
  "request_id": "req-9b8c2f1e-45a0-421d-a0e1-95c0211d08e2",
  "event": "http_request_completed",
  "duration_ms": 14.20,
  "extra_fields": {
    "status_code": 202,
    "method": "POST",
    "path": "/api/v1/webhooks/github",
    "client_ip": "140.82.115.1"
  }
}
```

### Standardized Event Taxonomy
- `http_request_started` / `http_request_completed` / `http_request_failed`
- `webhook_received` / `webhook_signature_verified` / `webhook_replay_rejected`
- `review_job_queued` / `review_job_started` / `review_job_completed` / `review_job_failed`
- `ast_diff_parsed` / `line_index_constructed`
- `agent_comprehension_started` / `agent_specialist_completed`
- `adversarial_judge_gate_evaluated` / `candidate_finding_rejected`
- `approval_requested` / `approval_granted` / `approval_rejected` / `approval_stale`
- `github_review_published` / `github_publication_failed`
- `policy_evaluated` / `policy_action_denied`

---

## 2. Distributed Correlation ID Tracing

CodeGuard propagates a continuous causal correlation trace across all asynchronous processes:

```
[Inbound HTTP Request] (X-Request-ID: req-12345)
          │
          ▼
     request_id: "req-12345"
          │
          ▼ Enqueued to Redis Celery
        job_id: "job-87654"
          │
          ▼ LangGraph Multi-Agent Run
     agent_run_id: "agent-run-33211"
          │
          ▼ Candidate Findings Generated
      finding_id: "fnd-00123"
          │
          ▼ Adversarial Judge Evaluation
       judge_id: "judge-99881"
          │
          ▼ Human Approval Request
     approval_id: "appr-44552"
          │
          ▼ Publication Service (Bound to Head SHA)
  publication_id: "pub-77889"
          │
          ▼ GitHub Cloud Review Comment
    github_id: 198273645
```

### Diagnostic Trace Recovery Query
To reconstruct the entire history of an incident or PR review:
```sql
SELECT
    j.id AS job_id,
    j.status AS job_status,
    j.created_at AS queued_at,
    a.id AS approval_id,
    a.status AS approval_status,
    p.id AS publication_id,
    p.github_review_id,
    p.status AS publication_status
FROM review_jobs j
LEFT JOIN approval_requests a ON a.review_job_id = j.id
LEFT JOIN github_review_publications p ON p.review_job_id = j.id
WHERE j.id = 'YOUR_JOB_ID';
```

---

## 3. Token Accounting & Gemini Cost Metrics

Every Gemini LLM call records prompt and completion token counts and computes financial cost in real-time:

### Cost Calculation Formulas
- **Fast Tier (`gemini-2.5-flash`)**:
  - Input: `$0.075` per 1,000,000 tokens (`$0.000000075` / token)
  - Output: `$0.300` per 1,000,000 tokens (`$0.000000300` / token)
- **Reasoning Tier (`gemini-2.5-pro`)**:
  - Input: `$1.250` per 1,000,000 tokens (`$0.000001250` / token)
  - Output: `$5.000` per 1,000,000 tokens (`$0.000005000` / token)

### Telemetry Record Example
```json
{
  "event": "llm_call_completed",
  "model": "gemini-2.5-flash",
  "tier": "fast",
  "input_tokens": 1240,
  "output_tokens": 312,
  "cost_usd": 0.0001866,
  "duration_ms": 782.4
}
```

---

## 4. Latency & Performance Baselines

| Operation | Baseline Target | Verified Staging Metric | SLA / Threshold |
|---|---|---|---|
| Health Probe (`/api/v1/health`) | < 10 ms | 5.02 ms | 50 ms |
| Liveness Probe (`/api/v1/live`) | < 10 ms | 4.98 ms | 50 ms |
| Readiness Probe (`/api/v1/ready`) | < 20 ms | 12.85 ms | 100 ms |
| GitHub Webhook Ingestion & Ack | < 50 ms | 14.20 ms | 200 ms |
| HMAC-SHA256 Signature Verify | < 1 ms | 0.031 ms | 5 ms |
| Tree-sitter Unified Diff Indexing | < 30 ms | 18.40 ms | 200 ms |
| Adversarial Judge 5-Gate Filter | < 50 ms | 22.10 ms | 150 ms |
| Zero-Trust Policy Authorization | < 5 ms | 0.002 ms | 20 ms |
| Full End-to-End Review (Mock/Cached) | < 3000 ms | 2032.0 ms | 10,000 ms |
