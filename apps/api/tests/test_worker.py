"""Tests for background review job worker execution, artifact persistence, and error handling."""

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import GitHubAPIError, GitHubNotFoundError
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_artifact import ArtifactType, ReviewArtifact
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.services.review_job_service import ReviewJobService
from app.workers.tasks import run_review_job_sync


@pytest.fixture
def populated_job(db_session: Session) -> ReviewJob:
    """Fixture to set up Organization, Repository, PullRequest, and ReviewJob."""
    org = Organization(
        github_installation_id=98765,
        github_account_id=54321,
        github_account_login="acme-corp",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=112233,
        owner="acme-corp",
        name="payment-service",
        full_name="acme-corp/payment-service",
        default_branch="main",
        is_private=True,
    )
    db_session.add(repo)
    db_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=889900,
        number=42,
        title="Refactor invoice charge retry logic",
        description="Implements exponential backoff on stripe gateway charges.",
        author_login="lead-dev",
        base_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        state="open",
        is_draft=False,
    )
    db_session.add(pr)
    db_session.flush()

    job = ReviewJob(
        pull_request_id=pr.id,
        status=ReviewJobStatus.PENDING,
        trigger="webhook:opened",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    return job


def test_review_job_successful_execution(db_session: Session, populated_job: ReviewJob) -> None:
    """Worker should successfully execute job, persist metadata & diff artifacts, and mark COMPLETED."""
    result = run_review_job_sync(populated_job.id, db_session)
    assert result["status"] == "success"
    assert result["job_status"] == "COMPLETED"

    # Verify ReviewJob updated in DB
    db_session.refresh(populated_job)
    assert populated_job.status == ReviewJobStatus.COMPLETED
    assert populated_job.started_at is not None
    assert populated_job.completed_at is not None
    assert populated_job.error_message is None

    # Verify Artifacts persisted (Phase 2 generates 9 artifacts)
    artifacts = (
        db_session.query(ReviewArtifact)
        .filter_by(review_job_id=populated_job.id)
        .order_by(ReviewArtifact.artifact_type)
        .all()
    )
    assert len(artifacts) == 9

    # Verify DIFF artifact
    diff_artifact = next(a for a in artifacts if a.artifact_type == ArtifactType.DIFF)
    assert "diff --git" in diff_artifact.content
    assert diff_artifact.metadata_json["byte_size"] > 0
    assert diff_artifact.metadata_json["line_count"] > 0

    # Verify PR_METADATA artifact
    meta_artifact = next(a for a in artifacts if a.artifact_type == ArtifactType.PR_METADATA)
    assert "Pull Request #42" in meta_artifact.content
    assert meta_artifact.metadata_json["github_pr_id"] is not None

    # Verify Phase 2 Code Intelligence Artifacts
    artifact_types = {a.artifact_type for a in artifacts}
    assert ArtifactType.PARSED_DIFF in artifact_types
    assert ArtifactType.CHANGED_LINE_INDEX in artifact_types
    assert ArtifactType.AST_CHUNKS in artifact_types
    assert ArtifactType.SYMBOL_INDEX in artifact_types
    assert ArtifactType.REFERENCE_INDEX in artifact_types
    assert ArtifactType.CONTEXT_MAP in artifact_types
    assert ArtifactType.PARSER_DIAGNOSTICS in artifact_types


def test_review_job_idempotent_reexecution(db_session: Session, populated_job: ReviewJob) -> None:
    """Re-executing an already COMPLETED review job should safely skip reprocessing."""
    # First execution
    run_review_job_sync(populated_job.id, db_session)
    db_session.refresh(populated_job)
    first_completed_at = populated_job.completed_at

    # Second execution attempt
    run_review_job_sync(populated_job.id, db_session)
    db_session.refresh(populated_job)

    assert populated_job.status == ReviewJobStatus.COMPLETED
    assert populated_job.completed_at == first_completed_at

    # No duplicate artifacts created
    count = db_session.query(ReviewArtifact).filter_by(review_job_id=populated_job.id).count()
    assert count == 9


@pytest.mark.asyncio
async def test_review_job_failure_handling(
    db_session: Session, populated_job: ReviewJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permanent error during execution should mark job as FAILED and record error message."""
    service = ReviewJobService(db_session)

    # Simulate GitHub 404
    async def mock_get_pr(*args, **kwargs):
        raise GitHubNotFoundError("Pull request not found")

    monkeypatch.setattr(service.github, "get_pull_request", mock_get_pr)

    job = await service.execute_job(populated_job.id)
    assert job.status == ReviewJobStatus.FAILED
    assert job.error_message is not None
    assert "GitHubNotFoundError" in job.error_message
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_review_job_transient_error_reraises(
    db_session: Session, populated_job: ReviewJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transient retryable errors must re-raise so worker task can backoff and retry."""
    service = ReviewJobService(db_session)

    # Simulate GitHub 502 Bad Gateway
    async def mock_transient_error(*args, **kwargs):
        raise GitHubAPIError("Gateway Timeout from GitHub", status_code=504, retryable=True)

    monkeypatch.setattr(service.github, "get_pull_request", mock_transient_error)

    with pytest.raises(GitHubAPIError) as exc_info:
        await service.execute_job(populated_job.id)

    assert exc_info.value.retryable is True
    # DB record should also record failure attempt
    db_session.refresh(populated_job)
    assert populated_job.status == ReviewJobStatus.FAILED
    assert populated_job.error_message is not None
    assert "Gateway Timeout" in populated_job.error_message
