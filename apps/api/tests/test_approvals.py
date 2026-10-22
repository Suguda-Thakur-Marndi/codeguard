"""Tests for human approval workflow and endpoints."""


import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.approval_request import ApprovalStatus
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.services.approval_service import ApprovalService


@pytest.fixture
def test_setup(db_session: Session) -> dict:
    org = Organization(
        github_installation_id=12345,
        github_account_id=67890,
        github_account_login="acme-corp",
    )
    db_session.add(org)
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=112233,
        owner="acme-corp",
        name="core-service",
        full_name="acme-corp/core-service",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=99001,
        number=101,
        title="Add payment refund",
        author_login="octocat",
        base_sha="base123456",
        head_sha="head123456",
    )
    db_session.add(pr)
    db_session.flush()

    job = ReviewJob(
        pull_request_id=pr.id,
        status=ReviewJobStatus.COMPLETED,
    )
    db_session.add(job)
    db_session.commit()

    return {"org": org, "repo": repo, "pr": pr, "job": job}


def test_approval_lifecycle(db_session: Session, test_setup: dict) -> None:
    service = ApprovalService(db_session)
    setup = test_setup

    # 1. Create approval request
    req = service.create_approval_request(
        organization_id=setup["org"].id,
        repository_id=setup["repo"].id,
        pull_request_id=setup["pr"].id,
        review_job_id=setup["job"].id,
        head_sha=setup["pr"].head_sha,
        requested_action="COMMENT",
        risk_level="CONSEQUENTIAL",
        requested_by="security-agent",
        expiry_minutes=60,
    )
    assert req.status == ApprovalStatus.PENDING
    assert req.head_sha == "head123456"

    # 2. Block AI agent from approving its own action
    with pytest.raises(ValueError, match="AI agents cannot approve"):
        service.approve_request(
            approval_id=req.id,
            approver_principal_id="security-agent",
            approver_role="REVIEWER",
            is_ai_agent=True,
        )

    # 3. Block unauthorized role (MEMBER)
    with pytest.raises(ValueError, match="not authorized to approve"):
        service.approve_request(
            approval_id=req.id,
            approver_principal_id="bob-member",
            approver_role="MEMBER",
            is_ai_agent=False,
        )

    # 4. Human Reviewer successfully approves
    approved = service.approve_request(
        approval_id=req.id,
        approver_principal_id="alice-reviewer",
        approver_role="REVIEWER",
        is_ai_agent=False,
        comment="LGTM, valid finding verified.",
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.approved_by == "alice-reviewer"
    assert approved.reason == "LGTM, valid finding verified."


def test_stale_commit_invalidates_approval(db_session: Session, test_setup: dict) -> None:
    service = ApprovalService(db_session)
    setup = test_setup

    req = service.create_approval_request(
        organization_id=setup["org"].id,
        repository_id=setup["repo"].id,
        pull_request_id=setup["pr"].id,
        review_job_id=setup["job"].id,
        head_sha=setup["pr"].head_sha,
        requested_action="REQUEST_CHANGES",
    )

    # Developer pushes new commit: head SHA moves
    setup["pr"].head_sha = "newcommit789"
    db_session.commit()

    with pytest.raises(ValueError, match="STALE"):
        service.approve_request(
            approval_id=req.id,
            approver_principal_id="alice-reviewer",
            approver_role="REVIEWER",
            is_ai_agent=False,
        )

    db_session.refresh(req)
    assert req.status == ApprovalStatus.CANCELLED


def test_approval_api_endpoints(client: TestClient, db_session: Session, test_setup: dict) -> None:
    service = ApprovalService(db_session)
    setup = test_setup

    req = service.create_approval_request(
        organization_id=setup["org"].id,
        repository_id=setup["repo"].id,
        pull_request_id=setup["pr"].id,
        review_job_id=setup["job"].id,
        head_sha=setup["pr"].head_sha,
    )

    # GET /approvals with pagination
    res = client.get("/api/v1/approvals?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert "total_pages" in data

    # GET /approvals/{id}
    res_single = client.get(f"/api/v1/approvals/{req.id}")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == req.id

    # POST /approvals/{id}/reject
    res_reject = client.post(
        f"/api/v1/approvals/{req.id}/reject",
        json={"reason": "False positive; existing guard covers this path."},
        headers={"x-user-id": "reviewer-1", "x-user-role": "REVIEWER"},
    )
    assert res_reject.status_code == 200
    assert res_reject.json()["approval_status"] == "REJECTED"
