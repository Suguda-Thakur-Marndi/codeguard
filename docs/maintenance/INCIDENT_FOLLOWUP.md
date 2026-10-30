# CodeGuard — Incident Follow-Up & Post-Mortem Guidelines

## 1. Prime Directive: Blameless Post-Mortem Culture

When a production incident, security anomaly, or review failure occurs, the maintenance engineering team conducts a **Blameless Root Cause Analysis (RCA)**. The objective is to identify systemic vulnerabilities, improve automated regression testing, and harden architectural boundaries—never to assign personal fault.

---

## 2. Standard Incident Lifecycle

```text
1. DETECTION & TRIAGE
   - Alert triggered or customer report received.
   - Severity assigned (P0: System Down / Data Breach, P1: Review Degradation, P2: Minor Defect).

2. MITIGATION & STABILIZATION
   - Apply rollback or failover runbook to restore service stability.
   - Preserve error logs, database states, and correlation IDs for analysis.

3. ROOT CAUSE INVESTIGATION
   - Reconstruct timeline using correlation IDs across API, Celery, and database logs.
   - Formulate 5 Whys analysis to uncover latent flaws.

4. REGRESSION TEST AUTHORING
   - Author a permanent regression test reproducing the exact failure mode.

5. PERMANENT REMEDIATION
   - Deploy minimal code or configuration fix verified by the new regression test.

6. POST-MORTEM PUBLICATION
   - Publish incident report to docs/maintenance/incidents/ within 48 hours.
```

---

## 3. Correlation ID & Observability Reconstruction

Every request and asynchronous job in CodeGuard carries standard correlation headers:

| Identifier | Source | Scope | Log Key |
| :--- | :--- | :--- | :--- |
| `request_id` | FastAPI middleware / Ingress | HTTP API request/response cycle | `request_id` |
| `event_id` | GitHub Webhook Header (`X-GitHub-Delivery`)| Webhook payload ingestion | `delivery_id` |
| `job_id` | `ReviewJob` record creation | Celery asynchronous review task | `job_id` |
| `review_id` | Multi-agent review pipeline | Findings, judge verdicts, publications | `review_id` |
| `approval_id` | Human approval creation | Cryptographic sign-off lifecycle | `approval_id` |

### Invariant: Secret Sanitization in Telemetry
Logs and telemetry must never output:
- Unmasked API keys (`GEMINI_API_KEY`, `GITHUB_WEBHOOK_SECRET`)
- Private keys (`GITHUB_PRIVATE_KEY`)
- Authorization Bearer tokens
- Database passwords in connection strings

Any incident where a credential is discovered in logs requires immediate key revocation, log purging, and an emergency patch to `app.core.security.mask_secret`.

---

## 4. Alert Quality & Tuning Standards

Alerts must generate actionable signals, not background noise. Every production alert in Prometheus / Alertmanager must satisfy:

1. **Concrete Actionable Response**: An alert that fires must direct the on-call engineer to a specific runbook in `docs/maintenance/MAINTENANCE_RUNBOOK.md`.
2. **Tested Trigger Conditions**: Alerts must be validated using synthetic failure injection tests in staging before promotion.
3. **De-duplication & Flap Suppression**: Alerts must enforce a minimum duration (e.g. `for: 5m`) to suppress transient network blips.
4. **Dead Alert Deprecation**: Any alert that has not fired meaningfully or whose failure mode is handled automatically by retries must be reviewed and removed.

---

## 5. Post-Mortem Report Template

Every incident post-mortem must follow this schema:

```markdown
# Incident Post-Mortem: [INC-YYYYMMDD-ID]

**Date**: YYYY-MM-DD  
**Severity**: [P0 | P1 | P2]  
**Lead Investigator**: [Name / Role]  
**Duration**: [X minutes]  
**Impact**: [Detailed user-facing impact]

## 1. Timeline (UTC)
- **HH:MM** - Anomaly detected via alert [AlertName].
- **HH:MM** - On-call engineer acknowledged incident.
- **HH:MM** - Mitigation applied [describe action].
- **HH:MM** - Service restored and verified healthy.

## 2. Root Cause Analysis (5 Whys)
1. Why did the review fail? [Finding was rejected]
2. Why was finding rejected? [Line index miscalculated]
3. Why was line index miscalculated? [Tree-sitter parser failed on specific syntax]
4. Why did parser fail? [Grammar binding did not handle edge-case syntax]
5. Why was this not caught? [Test suite lacked that specific syntax fixture]

## 3. Corrective Action Items
- [ ] Add regression test in `apps/api/tests/test_invariants_phase17.py` (Owner: Backend Agent, Due: Date)
- [ ] Deploy fix to Tree-sitter wrapper (Owner: Code Intel Agent, Due: Date)
- [ ] Tune alert threshold for failed review jobs (Owner: DevOps Agent, Due: Date)
```
