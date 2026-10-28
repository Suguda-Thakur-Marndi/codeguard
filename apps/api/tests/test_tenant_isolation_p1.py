"""Regression test suite for P1-A: Multi-Tenant Isolation.

Verifies:
1. Authorized access within the principal's own organization.
2. Denied access (403 Forbidden) to another organization's repositories and pull requests.
3. Denied access (403 Forbidden) to another organization's review jobs, artifacts, and findings.
4. Denied access to another organization's audit records and organization review policies.
5. Query parameter manipulation (e.g. ?organization_id=target) cannot bypass tenant boundaries.
6. Direct object ID requests across tenant boundaries are strictly rejected.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_artifact import ArtifactType, ReviewArtifact
from app.models.review_finding import FindingCategory, FindingSeverity, ReviewFindingModel
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.models.tool_audit import ToolExecutionAudit


@pytest.fixture
def two_tenants_fixture(db_session: Session) -> dict[str, Any]:
    """Create two completely isolated organizations with resources."""
    # Organization A
    org_a = Organization(
        github_installation_id=101010,
        github_account_id=1111,
        github_account_login="tenant-alpha",
        account_type="Organization",
    )
    # Organization B
    org_b = Organization(
        github_installation_id=202020,
        github_account_id=2222,
        github_account_login="tenant-beta",
        account_type="Organization",
    )
    db_session.add_all([org_a, org_b])
    db_session.flush()

    # Repositories
    repo_a = Repository(
        organization_id=org_a.id,
        github_repo_id=303030,
        owner="tenant-alpha",
        name="alpha-service",
        full_name="tenant-alpha/alpha-service",
        default_branch="main",
        is_private=True,
    )
    repo_b = Repository(
        organization_id=org_b.id,
        github_repo_id=404040,
        owner="tenant-beta",
        name="beta-service",
        full_name="tenant-beta/beta-service",
        default_branch="main",
        is_private=True,
    )
    db_session.add_all([repo_a, repo_b])
    db_session.flush()

    # Pull Requests
    pr_a = PullRequest(
        repository_id=repo_a.id,
        github_pr_id=505050,
        number=1,
        title="Alpha PR 1",
        author_login="alice",
        base_sha="0000000000000000000000000000000000000000",
        head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        state="open",
    )
    pr_b = PullRequest(
        repository_id=repo_b.id,
        github_pr_id=606060,
        number=2,
        title="Beta PR 2",
        author_login="bob",
        base_sha="0000000000000000000000000000000000000000",
        head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        state="open",
    )
    db_session.add_all([pr_a, pr_b])
    db_session.flush()

    # Review Jobs
    job_a = ReviewJob(
        pull_request_id=pr_a.id,
        status=ReviewJobStatus.COMPLETED,
        trigger="webhook:opened",
    )
    job_b = ReviewJob(
        pull_request_id=pr_b.id,
        status=ReviewJobStatus.COMPLETED,
        trigger="webhook:opened",
    )
    db_session.add_all([job_a, job_b])
    db_session.flush()

    # Artifacts
    artifact_a = ReviewArtifact(
        review_job_id=job_a.id,
        artifact_type=ArtifactType.DIFF,
        content="diff --git a/alpha.py b/alpha.py",
    )
    artifact_b = ReviewArtifact(
        review_job_id=job_b.id,
        artifact_type=ArtifactType.DIFF,
        content="diff --git a/beta.py b/beta.py",
    )
    db_session.add_all([artifact_a, artifact_b])
    db_session.flush()

    # Findings
    finding_a = ReviewFindingModel(
        review_job_id=job_a.id,
        file_path="alpha.py",
        line_number=10,
        title="SQL Injection in Alpha",
        description="Vulnerable query",
        impact="Allows data leakage",
        recommendation="Use parameterized queries",
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        agent_name="security",
    )
    finding_b = ReviewFindingModel(
        review_job_id=job_b.id,
        file_path="beta.py",
        line_number=20,
        title="Hardcoded secret in Beta",
        description="Leaked token",
        impact="Allows credential theft",
        recommendation="Store in environment secrets",
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        agent_name="security",
    )
    db_session.add_all([finding_a, finding_b])
    db_session.flush()

    from datetime import UTC, datetime

    # Audit records
    audit_a = ToolExecutionAudit(
        principal_id="user-alpha",
        organization_id=org_a.id,
        repository_id=repo_a.id,
        tool_name="get_pull_request",
        resource_type="repository",
        risk_level="READ_ONLY",
        authorization_decision="ALLOW",
        started_at=datetime.now(UTC),
    )
    audit_b = ToolExecutionAudit(
        principal_id="user-beta",
        organization_id=org_b.id,
        repository_id=repo_b.id,
        tool_name="get_pull_request",
        resource_type="repository",
        risk_level="READ_ONLY",
        authorization_decision="ALLOW",
        started_at=datetime.now(UTC),
    )
    db_session.add_all([audit_a, audit_b])
    db_session.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "repo_a": repo_a,
        "repo_b": repo_b,
        "pr_a": pr_a,
        "pr_b": pr_b,
        "job_a": job_a,
        "job_b": job_b,
        "artifact_a": artifact_a,
        "artifact_b": artifact_b,
        "finding_a": finding_a,
        "finding_b": finding_b,
        "audit_a": audit_a,
        "audit_b": audit_b,
    }


def test_authorized_access_within_tenant(client: TestClient, two_tenants_fixture: dict[str, Any]) -> None:
    """User in Tenant Alpha can successfully view and access Tenant Alpha's resources."""
    fix = two_tenants_fixture
    headers_alpha = {"X-Organization-Id": fix["org_a"].id, "X-User-Role": "MEMBER"}

    # List repositories: receives only alpha repo
    resp = client.get("/api/v1/repositories", headers=headers_alpha)
    assert resp.status_code == 200
    repo_ids = [r["id"] for r in resp.json()["items"]]
    assert fix["repo_a"].id in repo_ids
    assert fix["repo_b"].id not in repo_ids

    # Detail repository
    resp = client.get(f"/api/v1/repositories/{fix['repo_a'].id}", headers=headers_alpha)
    assert resp.status_code == 200
    assert resp.json()["id"] == fix["repo_a"].id

    # List pull requests: receives only alpha PR
    resp = client.get("/api/v1/pull-requests", headers=headers_alpha)
    assert resp.status_code == 200
    pr_ids = [p["id"] for p in resp.json()["items"]]
    assert fix["pr_a"].id in pr_ids
    assert fix["pr_b"].id not in pr_ids

    # Detail pull request
    resp = client.get(f"/api/v1/pull-requests/{fix['pr_a'].id}", headers=headers_alpha)
    assert resp.status_code == 200
    assert resp.json()["id"] == fix["pr_a"].id

    # Detail review job
    resp = client.get(f"/api/v1/review-jobs/{fix['job_a'].id}", headers=headers_alpha)
    assert resp.status_code == 200

    # Detail finding
    resp = client.get(f"/api/v1/findings/{fix['finding_a'].id}", headers=headers_alpha)
    assert resp.status_code == 200

    # List audit events: receives only alpha audit
    resp = client.get("/api/v1/audit", headers=headers_alpha)
    assert resp.status_code == 200
    audit_ids = [a["id"] for a in resp.json()["items"]]
    assert fix["audit_a"].id in audit_ids
    assert fix["audit_b"].id not in audit_ids


def test_cross_tenant_repository_access_denied(client: TestClient, two_tenants_fixture: dict[str, Any]) -> None:
    """User in Tenant Alpha is denied access to Tenant Beta's repositories."""
    fix = two_tenants_fixture
    headers_alpha = {"X-Organization-Id": fix["org_a"].id, "X-User-Role": "MEMBER"}

    # Attempt to read Beta repository details
    resp = client.get(f"/api/v1/repositories/{fix['repo_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Attempt to delete Beta repository
    resp = client.delete(f"/api/v1/repositories/{fix['repo_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]


def test_cross_tenant_pull_request_access_denied(client: TestClient, two_tenants_fixture: dict[str, Any]) -> None:
    """User in Tenant Alpha is denied access to Tenant Beta's pull requests."""
    fix = two_tenants_fixture
    headers_alpha = {"X-Organization-Id": fix["org_a"].id, "X-User-Role": "MEMBER"}

    # Attempt to read Beta PR details
    resp = client.get(f"/api/v1/pull-requests/{fix['pr_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Attempt to list Beta PR reviews
    resp = client.get(f"/api/v1/pull-requests/{fix['pr_b'].id}/reviews", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Attempt to query pull requests with repository_id of Beta
    resp = client.get(f"/api/v1/pull-requests?repository_id={fix['repo_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]


def test_cross_tenant_review_and_finding_access_denied(client: TestClient, two_tenants_fixture: dict[str, Any]) -> None:
    """User in Tenant Alpha is denied access to Tenant Beta's review jobs and findings."""
    fix = two_tenants_fixture
    headers_alpha = {"X-Organization-Id": fix["org_a"].id, "X-User-Role": "MEMBER"}

    # Review job detail
    resp = client.get(f"/api/v1/review-jobs/{fix['job_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Review job artifacts
    resp = client.get(f"/api/v1/review-jobs/{fix['job_b'].id}/artifacts", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Review job findings
    resp = client.get(f"/api/v1/review-jobs/{fix['job_b'].id}/findings", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Finding detail
    resp = client.get(f"/api/v1/findings/{fix['finding_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]


def test_cross_tenant_query_param_bypass_rejected(client: TestClient, two_tenants_fixture: dict[str, Any]) -> None:
    """Attempting to supply another organization's ID in query parameters is rejected."""
    fix = two_tenants_fixture
    headers_alpha = {"X-Organization-Id": fix["org_a"].id, "X-User-Role": "MEMBER"}

    # Repositories query param bypass attempt
    resp = client.get(f"/api/v1/repositories?organization_id={fix['org_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Audit query param bypass attempt
    resp = client.get(f"/api/v1/audit?organization_id={fix['org_b'].id}", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Organization policies bypass attempt
    resp = client.get(f"/api/v1/organizations/{fix['org_b'].id}/policies", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]


def test_cross_tenant_code_intelligence_access_denied(client: TestClient, two_tenants_fixture: dict[str, Any]) -> None:
    """User in Tenant Alpha cannot inspect AST, symbols, or context for Tenant Beta's code."""
    fix = two_tenants_fixture
    headers_alpha = {"X-Organization-Id": fix["org_a"].id, "X-User-Role": "MEMBER"}

    # Index status
    resp = client.get(f"/api/v1/repositories/{fix['repo_b'].id}/index", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Symbols list
    resp = client.get(f"/api/v1/repositories/{fix['repo_b'].id}/symbols", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Context query
    resp = client.get(
        f"/api/v1/repositories/{fix['repo_b'].id}/context?changed_file=beta.py",
        headers=headers_alpha,
    )
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]


def test_cross_tenant_review_subresources_denied(client: TestClient, two_tenants_fixture: dict[str, Any]) -> None:
    """User in Tenant Alpha cannot access verification summary, traces, or rerun Tenant Beta's jobs."""
    fix = two_tenants_fixture
    headers_alpha = {"X-Organization-Id": fix["org_a"].id, "X-User-Role": "MEMBER"}

    # Verification summary
    resp = client.get(f"/api/v1/review-jobs/{fix['job_b'].id}/verification", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Execution trace
    resp = client.get(f"/api/v1/review-jobs/{fix['job_b'].id}/trace", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Judge runs
    resp = client.get(f"/api/v1/review-jobs/{fix['job_b'].id}/judge", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Finding evidence
    resp = client.get(f"/api/v1/findings/{fix['finding_b'].id}/evidence", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

    # Re-run review job
    resp = client.post(f"/api/v1/review-jobs/{fix['job_b'].id}/rerun", headers=headers_alpha)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["detail"]

