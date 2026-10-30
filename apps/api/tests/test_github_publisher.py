"""Tests for atomic GitHub review publisher, line validation, idempotency, and endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.github.publisher import GitHubReviewPublisher
from app.models.approval_request import ApprovalStatus
from app.models.github_publication import PublicationStatus
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_finding import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    ReviewFindingModel,
)
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.services.publication_service import PublicationService


@pytest.fixture
def pub_setup(db_session: Session) -> dict:
    org = Organization(
        github_installation_id=9876,
        github_account_id=5432,
        github_account_login="acme-corp",
    )
    db_session.add(org)
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=98765,
        owner="acme-corp",
        name="billing-service",
        full_name="acme-corp/billing-service",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=77001,
        number=42,
        title="Fix refund calculation",
        author_login="octocat",
        base_sha="base_sha_123",
        head_sha="head_sha_456",
    )
    db_session.add(pr)
    db_session.flush()

    job = ReviewJob(
        pull_request_id=pr.id,
        status=ReviewJobStatus.COMPLETED,
    )
    db_session.add(job)
    db_session.flush()

    finding = ReviewFindingModel(
        review_job_id=job.id,
        agent_name="security_agent",
        file_path="src/billing.py",
        line_number=10,
        side="RIGHT",
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        final_severity="HIGH",
        title="Unauthenticated access",
        description="Missing permissions check on billing refund endpoint",
        impact="Critical financial breach",
        recommendation="Verify user permissions before issuing refund",
        status=FindingStatus.PUBLISHABLE,
    )
    db_session.add(finding)
    db_session.commit()

    return {"org": org, "repo": repo, "pr": pr, "job": job, "finding": finding}


@pytest.mark.asyncio
async def test_atomic_review_builder() -> None:
    findings = [
        {
            "final_severity": "HIGH",
            "category": "SECURITY",
            "title": "SQL Injection",
            "description": "User input passed to cursor without escaping",
            "impact": "Data exfiltration",
            "recommendation": "Use parameterized queries",
            "file_path": "src/db.py",
            "line_number": 55,
            "side": "RIGHT",
        }
    ]
    summary = GitHubReviewPublisher.build_review_summary(findings, action="COMMENT")
    assert "CodeGuard Verified Review" in summary
    assert "High Severity" in summary
    assert "Security Vulnerabilities**: 1" in summary

    comment_body = GitHubReviewPublisher.format_inline_comment_body(findings[0])
    assert "[HIGH] SQL Injection" in comment_body
    assert "Recommendation" in comment_body


@pytest.mark.asyncio
async def test_stale_head_sha_aborts() -> None:
    pub = GitHubReviewPublisher()
    res = await pub.publish_atomic_review(
        owner="acme",
        repo="service",
        pull_number=42,
        verified_head_sha="commit_old",
        current_head_sha="commit_new",
        findings=[],
    )
    assert not res.success
    assert res.status == "STALE"
    assert "mismatch" in (res.error_message or "")


@pytest.mark.asyncio
async def test_invalid_diff_line_rejected() -> None:
    pub = GitHubReviewPublisher()
    valid_lines = {"src/app.py": {"RIGHT": [1, 2, 3]}}
    findings = [{"file_path": "src/app.py", "line_number": 999, "side": "RIGHT"}]

    res = await pub.publish_atomic_review(
        owner="acme",
        repo="service",
        pull_number=42,
        verified_head_sha="sha1",
        current_head_sha="sha1",
        findings=findings,
        valid_lines_by_file=valid_lines,
    )
    assert not res.success
    assert res.status == "FAILED"
    assert "Invalid diff line coordinate" in (res.error_message or "")


@pytest.mark.asyncio
async def test_publication_service_e2e_flow(db_session: Session, pub_setup: dict) -> None:
    service = PublicationService(db_session)
    setup = pub_setup

    # 1. Prepare publication -> High severity triggers APPROVAL_REQUIRED
    pub, approval = service.prepare_publication(review_job_id=setup["job"].id, action="COMMENT")
    assert pub.status == PublicationStatus.APPROVAL_REQUIRED
    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING

    # 2. Human Reviewer approves
    approval.status = ApprovalStatus.APPROVED
    approval.approved_by = "alice-reviewer"
    db_session.commit()

    # 3. Execute publication
    completed_pub = await service.execute_publication(publication_id=pub.id)
    assert completed_pub.status == PublicationStatus.PUBLISHED
    assert completed_pub.github_review_id is not None
    assert completed_pub.comment_count == 1

    # 4. Idempotency test: Second execution returns existing result without duplicating
    dup_pub = await service.execute_publication(publication_id=pub.id)
    assert dup_pub.id == completed_pub.id
    assert dup_pub.github_review_id == completed_pub.github_review_id


def test_api_publication_endpoints(client: TestClient, db_session: Session, pub_setup: dict) -> None:
    job_id = pub_setup["job"].id

    # 1. GET publication (initially None)
    get_res = client.get(f"/api/v1/review-jobs/{job_id}/publication")
    assert get_res.status_code == 200
    assert get_res.json()["publication"] is None

    # 2. POST /review-jobs/{id}/publication/request-approval
    req_res = client.post(
        f"/api/v1/review-jobs/{job_id}/publication/request-approval",
        json={"action": "COMMENT"},
    )
    assert req_res.status_code == 200
    req_data = req_res.json()
    assert "approval_id" in req_data
    approval_id = req_data["approval_id"]
    assert approval_id is not None

    # 3. Direct publication without human approval is rejected (Policy enforcement)
    unapproved_res = client.post(
        f"/api/v1/review-jobs/{job_id}/publication/publish",
        json={"action": "COMMENT"},
    )
    assert unapproved_res.status_code == 400
    assert "requires human" in unapproved_res.json()["detail"].lower()

    # 4. Human reviewer approves the request
    approve_res = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"comment": "Approved by security lead"},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "success"
    assert approve_res.json()["approval_status"] == "APPROVED"

    # 5. Now POST /review-jobs/{id}/publication/publish succeeds (or returns idempotent published state)
    pub_res = client.post(
        f"/api/v1/review-jobs/{job_id}/publication/publish",
        json={"action": "COMMENT"},
    )
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["status"] in ["PUBLISHED", "ALREADY_PUBLISHED"]
    assert "publication_id" in pub_data


