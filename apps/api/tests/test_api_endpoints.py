"""Tests for REST API collection, detail, pagination, and authorization behavior."""

from datetime import UTC

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_artifact import ArtifactType, ReviewArtifact
from app.models.review_job import ReviewJob, ReviewJobStatus


def seed_test_entities(db_session: Session) -> dict:
    """Helper to populate database with sample records."""
    org = Organization(
        github_installation_id=777,
        github_account_id=888,
        github_account_login="github-enterprise",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=999,
        owner="github-enterprise",
        name="billing-api",
        full_name="github-enterprise/billing-api",
        default_branch="main",
        is_private=True,
    )
    db_session.add(repo)
    db_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=1001,
        number=15,
        title="Upgrade stripe-node SDK to v15",
        description="Breaking changes migrated for new webhook signature events.",
        author_login="octo-bot",
        base_sha="1111111111111111111111111111111111111111",
        head_sha="2222222222222222222222222222222222222222",
        state="open",
        is_draft=False,
    )
    db_session.add(pr)
    db_session.flush()

    job = ReviewJob(
        pull_request_id=pr.id,
        status=ReviewJobStatus.COMPLETED,
        trigger="webhook:opened",
    )
    db_session.add(job)
    db_session.flush()

    artifact = ReviewArtifact(
        review_job_id=job.id,
        artifact_type=ArtifactType.DIFF,
        content="diff --git a/package.json b/package.json\n+ stripe: 15.0.0",
        metadata_json={"line_count": 2},
    )
    db_session.add(artifact)
    db_session.commit()

    return {"org": org, "repo": repo, "pr": pr, "job": job, "artifact": artifact}


def test_list_organizations(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/organizations returns paginated items."""
    seed_test_entities(db_session)
    response = client.get("/api/v1/organizations?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert len(data["items"]) >= 1
    assert data["items"][0]["github_account_login"] == "github-enterprise"


def test_list_repositories_and_filter(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/repositories with pagination and filtering."""
    seeds = seed_test_entities(db_session)
    response = client.get(f"/api/v1/repositories?organization_id={seeds['org'].id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "billing-api"


def test_get_repository_by_id(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/repositories/{id} returns repo with organization."""
    seeds = seed_test_entities(db_session)
    response = client.get(f"/api/v1/repositories/{seeds['repo'].id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == seeds["repo"].id
    assert data["organization"]["github_account_login"] == "github-enterprise"


def test_get_repository_not_found(client: TestClient) -> None:
    """Non-existent repo ID returns 404."""
    response = client.get("/api/v1/repositories/non-existent-id")
    assert response.status_code == 404


def test_list_pull_requests_and_filter(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/pull-requests with pagination and state filter."""
    seeds = seed_test_entities(db_session)
    response = client.get(f"/api/v1/pull-requests?repository_id={seeds['repo'].id}&state=open")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["number"] == 15
    assert data["items"][0]["state"] == "open"


def test_get_pull_request_detail(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/pull-requests/{id} returns PR with latest review status."""
    seeds = seed_test_entities(db_session)
    response = client.get(f"/api/v1/pull-requests/{seeds['pr'].id}")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Upgrade stripe-node SDK to v15"
    assert data["latest_review_status"] == "COMPLETED"


def test_get_pull_request_reviews(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/pull-requests/{id}/reviews returns review job history."""
    seeds = seed_test_entities(db_session)
    response = client.get(f"/api/v1/pull-requests/{seeds['pr'].id}/reviews")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "COMPLETED"


def test_get_review_job_and_artifacts(client: TestClient, db_session: Session) -> None:
    """Verify review job and artifact retrieval endpoints."""
    seeds = seed_test_entities(db_session)

    # 1. Job details
    job_res = client.get(f"/api/v1/review-jobs/{seeds['job'].id}")
    assert job_res.status_code == 200
    assert job_res.json()["id"] == seeds["job"].id
    assert job_res.json()["status"] == "COMPLETED"

    # 2. Artifacts
    art_res = client.get(f"/api/v1/review-jobs/{seeds['job'].id}/artifacts")
    assert art_res.status_code == 200
    artifacts = art_res.json()
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "DIFF"
    assert "stripe: 15.0.0" in artifacts[0]["content"]


def test_auth_rejection_when_bypass_disabled(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    """When DEV_AUTH_BYPASS is disabled and no token is provided, requests must be rejected with 401."""
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    response = client.get("/api/v1/organizations")
    assert response.status_code == 401
    assert "Authentication credentials required" in response.json()["detail"]


def test_phase3_review_job_endpoints(client: TestClient, db_session: Session) -> None:
    """Verify Phase 3 endpoints for agent runs, findings, traces, usage, and rerun."""
    from datetime import datetime

    from app.models.agent_run import AgentRun
    from app.models.agent_trace import AgentTrace
    from app.models.review_finding import ReviewFindingModel

    seeds = seed_test_entities(db_session)
    job_id = seeds["job"].id

    # 1. Seed AgentRun
    agent_run = AgentRun(
        review_job_id=job_id,
        agent_name="security",
        agent_version="1.0.0",
        model_name="gemini-2.5-pro",
        prompt_version="security.v1",
        status="COMPLETED",
        input_tokens=1500,
        output_tokens=300,
        total_tokens=1800,
        estimated_cost=0.003375,
        latency_ms=1250.0,
        retry_count=0,
    )
    db_session.add(agent_run)
    db_session.flush()

    # 2. Seed ReviewFindingModel
    finding = ReviewFindingModel(
        review_job_id=job_id,
        agent_run_id=agent_run.id,
        file_path="src/payment.py",
        line_number=45,
        side="RIGHT",
        category="SECURITY",
        severity="HIGH",
        title="Missing Auth Check",
        description="Missing role validation on refund flow",
        impact="Unauthorized refund execution",
        recommendation="Add auth check",
        confidence=0.92,
        evidence=[{"type": "CODE", "file": "src/payment.py", "description": "Refund call"}],
        agent_name="security",
        status="VALID",
    )
    db_session.add(finding)

    # 3. Seed AgentTrace
    trace = AgentTrace(
        review_job_id=job_id,
        node_name="specialists_dispatcher_node",
        agent_name="security",
        status="COMPLETED",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        duration_ms=1250.0,
        model_name="gemini-2.5-pro",
        input_tokens=1500,
        output_tokens=300,
        total_tokens=1800,
        retry_count=0,
    )
    db_session.add(trace)

    # Update job totals
    seeds["job"].total_tokens = 1800
    seeds["job"].estimated_cost = 0.003375
    seeds["job"].agents_executed = ["security"]
    db_session.commit()

    # Test GET /api/v1/review-jobs/{id}/agents
    agents_res = client.get(f"/api/v1/review-jobs/{job_id}/agents")
    assert agents_res.status_code == 200
    agents_data = agents_res.json()
    assert len(agents_data) == 1
    assert agents_data[0]["agent_name"] == "security"
    assert agents_data[0]["status"] == "COMPLETED"

    # Test GET /api/v1/review-jobs/{id}/findings
    findings_res = client.get(f"/api/v1/review-jobs/{job_id}/findings")
    assert findings_res.status_code == 200
    findings_data = findings_res.json()
    assert len(findings_data) == 1
    assert findings_data[0]["title"] == "Missing Auth Check"
    assert findings_data[0]["severity"] == "HIGH"
    assert findings_data[0]["file_path"] == "src/payment.py"

    # Test GET /api/v1/review-jobs/{id}/findings/{finding_id}
    finding_id = findings_data[0]["id"]
    single_res = client.get(f"/api/v1/review-jobs/{job_id}/findings/{finding_id}")
    assert single_res.status_code == 200
    assert single_res.json()["id"] == finding_id

    # Test GET /api/v1/review-jobs/{id}/trace
    trace_res = client.get(f"/api/v1/review-jobs/{job_id}/trace")
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert len(trace_data) == 1
    assert trace_data[0]["node_name"] == "specialists_dispatcher_node"

    # Test GET /api/v1/review-jobs/{id}/usage
    usage_res = client.get(f"/api/v1/review-jobs/{job_id}/usage")
    assert usage_res.status_code == 200
    usage_data = usage_res.json()
    assert usage_data["total_tokens"] == 1800
    assert usage_data["estimated_cost"] > 0
    assert len(usage_data["breakdown_by_agent"]) == 1

    # Test POST /api/v1/review-jobs/{id}/rerun
    rerun_res = client.post(f"/api/v1/review-jobs/{job_id}/rerun")
    assert rerun_res.status_code == 200
    rerun_data = rerun_res.json()
    assert rerun_data["id"] == job_id
    assert rerun_data["status"] == "COMPLETED"


def test_audit_events_pagination(client: TestClient, db_session: Session) -> None:
    from datetime import UTC, datetime
    from app.models.tool_audit import ToolExecutionAudit

    # Seed an audit record
    audit = ToolExecutionAudit(
        principal_id="user-123",
        organization_id="org-123",
        repository_id="repo-123",
        tool_name="git_diff_reader",
        resource_type="repository",
        resource_id="repo-123",
        risk_level="READ_ONLY",
        authorization_decision="ALLOW",
        execution_status="SUCCESS",
        started_at=datetime.now(UTC),
    )
    db_session.add(audit)
    db_session.commit()

    # Query with page & page_size
    res = client.get("/api/v1/audit?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert "total_pages" in data
    assert any(a["id"] == audit.id for a in data["items"])


