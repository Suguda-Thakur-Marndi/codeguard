# CodeGuard — Maintenance Ownership & Responsibility Matrix

**Document ID**: `DOC-OPS-OWNER-01`  
**Application Version**: `1.0.0`  
**Classification**: Organizational Governance & Escalation Directory  
**Last Verified**: 2026-09-29  

---

## 1. Ownership Principles

1. **Role-Based Accountability**: Responsibilities are assigned to functional engineering roles rather than individual employee names to ensure continuous institutional maintainability.
2. **Principle of Least Privilege**: Access to production infrastructure, cryptographic signing keys, and cloud billing accounts is strictly compartmentalized.
3. **Owner Authorization Gates**: Consequential actions (e.g. production deployments, credential rotations, database rollbacks, legal pilot authorizations) strictly require formal Project Owner sign-off.

---

## 2. Ownership & Responsibility Matrix

| Subsystem / Functional Domain | Primary Responsible Role | Secondary / Backup Role | Core Responsibilities |
| :--- | :--- | :--- | :--- |
| **Application Core & Backend** | **Backend Lead Engineer** | Fullstack Engineer | FastAPI routes, domain services, Pydantic schemas, Celery tasks, test suite maintenance. |
| **Frontend Web Application** | **Frontend Lead Engineer** | Fullstack Engineer | Next.js 15 SSR dashboard, UI component hierarchy, API client integration, approval interfaces. |
| **Cloud Infrastructure & Containers**| **DevOps / SRE Lead** | Infrastructure Engineer | Dockerfiles, Docker Compose, Kubernetes manifests, reverse proxy TLS, container scaling. |
| **Database & Schema Operations** | **Database Administrator** | Backend Lead Engineer | Alembic migrations, PostgreSQL connection tuning, backup verification, point-in-time recovery. |
| **GitHub App & Webhook Ingress** | **Integration Specialist** | DevOps / SRE Lead | GitHub App registration, RSA private key management, webhook secret rotation, API permissions. |
| **AI Provider & Model Operations** | **AI Engineering Lead** | Backend Lead Engineer | Gemini API budgeting, token monitoring, prompt registry optimization, specialist tuning. |
| **Zero-Trust Policy Governance** | **Security Lead Engineer** | Architect Agent | Zero-trust security policies, forbidden operations blocklists, tool schema validation, audit logs. |
| **Security & Incident Response** | **Chief Information Security Officer** | Security Lead Engineer | Threat modeling, secret management, CVE patching, red-team drills, incident triage. |
| **Dependency Health & Upgrades** | **Platform Maintainer** | QA / Testing Lead | Dependabot alerts review, package lockfile audits, breaking dependency migration testing. |
| **Releases, Rollbacks & Deployment**| **Release Manager** | Project Owner | Release tagging, changelog publication, pre-release smoke tests, emergency rollbacks. |

---

## 3. High-Consequence Action Authorization Directory

The following actions have significant operational, financial, or security impact and **STRICTLY REQUIRE EXPLICIT PROJECT OWNER AUTHORIZATION**:

| High-Consequence Action | Minimum Required Authority | Mandatory Pre-Conditions |
| :--- | :--- | :--- |
| **General Availability Production Release** | **Project Owner & Release Manager** | 100% pass on 27 SRE gates, completion of authorized 4-week pilot, signed QA sign-off. |
| **Customer Pilot Onboarding & Repo Access**| **Project Owner & Security Lead** | Signed Pilot Agreement, data processing addendum, repository scope boundaries verified. |
| **Production Database Downgrade / Drop** | **Project Owner & DBA Lead** | Full verified database snapshot verified via SHA-256 integrity checksum. |
| **Production Secret / RSA Key Revocation** | **Security Lead & DevOps Lead** | Staging validation of new key, coordinated zero-downtime rollover playbook executed. |
| **Modifying Forbidden Operations Blocklist**| **Project Owner & Security Lead** | Written security rationale, red-team penetration test of proposed exception. |
| **Gemini Daily Budget Expenditure Increase** | **Project Owner & AI Lead** | Business justification, token audit of preceding 30 days, billing alert thresholds updated. |

---

## 4. Escalation & Incident Triage Protocol

In the event of an operational degradation, security alert, or production outage:

1. **Severity 1 (Critical Outage / False Authorization / Data Breach)**:
   - *Escalation Time*: Immediate (< 15 minutes).
   - *Notified Roles*: Project Owner, Security Lead, DevOps / SRE Lead, Backend Lead.
   - *Action*: Execute emergency review publication kill-switch ([`docs/RUNBOOK.md`](file:///c:/Users/sugud/OneDrive/Documents/codeguard-ai/docs/RUNBOOK.md) Section 4.4).
2. **Severity 2 (Degraded Performance / Celery Queue Backlog / 429 Quota Alert)**:
   - *Escalation Time*: Within 1 hour.
   - *Notified Roles*: Backend Lead, DevOps / SRE Lead.
   - *Action*: Scale worker replicas or adjust rate limit backoff.
3. **Severity 3 (Minor UI Glitch / Non-Blocking Test Warning)**:
   - *Escalation Time*: Standard business hours.
   - *Notified Roles*: Primary Subsystem Owner.
   - *Action*: Triage during weekly sprint planning.
