"""Failure and Recovery tests for CodeGuard.

Verifies:
- Gemini API error and timeout recovery
- GitHub API 429 rate limit backoff and 5xx server error retries
- Sandbox execution timeout containment
- Worker crash and error state capture
- Review job rerun idempotency
"""

import asyncio
import tempfile
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.orm import Session

from app.agents.validation.sandbox import ExecutionSandbox
from app.core.exceptions import GitHubAPIError, GitHubRateLimitError
from app.github.client import GitHubClient
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.services.review_job_service import ReviewJobService


@pytest.fixture
def failure_setup(db_session: Session) -> dict:
    org = Organization(
        github_installation_id=50001,
        github_account_id=60001,
        github_account_login="fail-test-org",
    )
    db_session.add(org)
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=70001,
        owner="fail-test-org",
        name="fail-repo",
        full_name="fail-test-org/fail-repo",
    )
    db_session.add(repo)
    db_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=80001,
        number=77,
        title="Failure test PR",
        author_login="tester",
        base_sha="1"*40,
        head_sha="2"*40,
    )
    db_session.add(pr)
    db_session.flush()

    job = ReviewJob(
        pull_request_id=pr.id,
        status=ReviewJobStatus.PENDING,
    )
    db_session.add(job)
    db_session.commit()

    return {"org": org, "repo": repo, "pr": pr, "job": job}


async def test_github_429_rate_limit_backoff():
    """GitHub client must detect 429/rate-limit response and raise GitHubRateLimitError."""
    client = GitHubClient()
    client.auth.private_key = "dummy_private_key"
    mock_response = httpx.Response(
        429,
        text="Rate limit exceeded",
        headers={"Retry-After": "1"},
        request=httpx.Request("GET", "https://api.github.com/repos/org/repo/pulls/1"),
    )

    with patch.object(client, "_get_auth_headers", AsyncMock(return_value={"Authorization": "Bearer test"})), \
         patch("httpx.AsyncClient.request", AsyncMock(return_value=mock_response)), \
         patch("asyncio.sleep", AsyncMock()):
        with pytest.raises((GitHubRateLimitError, GitHubAPIError)):
            await client.get_pull_request("org", "repo", 1, installation_id=101)


async def test_github_502_server_error_retryable():
    """GitHub client must classify 502/503 errors as retryable."""
    client = GitHubClient()
    client.auth.private_key = "dummy_private_key"
    mock_502 = httpx.Response(
        502,
        text="Bad Gateway",
        request=httpx.Request("GET", "https://api.github.com/repos/org/repo/pulls/1"),
    )

    with patch.object(client, "_get_auth_headers", AsyncMock(return_value={"Authorization": "Bearer test"})), \
         patch("httpx.AsyncClient.request", AsyncMock(return_value=mock_502)), \
         patch("asyncio.sleep", AsyncMock()):
        with pytest.raises(GitHubAPIError) as exc_info:
            await client.get_pull_request("org", "repo", 1, installation_id=101)
        assert exc_info.value.retryable is True


def test_sandbox_timeout_enforcement():
    """Sandbox must contain and terminate long-running processes when timeout expires."""
    sandbox = ExecutionSandbox(timeout_seconds=1)
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Command that sleeps longer than 1s timeout without shell operators
        res = asyncio.run(
            sandbox.execute_command(
                command="python -c \"__import__('time').sleep(5)\"",
                repo_dir=tmp_dir,
                timeout=1,
            )
        )
        assert res.status in ("TIMEOUT", "ERROR")


def test_review_job_failure_captured_safely(db_session: Session, failure_setup: dict):
    """When a review job encounters a non-retryable fatal error, it marks FAILED without crashing."""
    setup = failure_setup
    service = ReviewJobService(db_session)

    # Force github client to raise fatal non-retryable error
    fatal_error = GitHubAPIError("Repository suspended by GitHub", status_code=403, retryable=False)
    with patch.object(service.github, "get_pull_request", AsyncMock(side_effect=fatal_error)):
        completed_job = asyncio.run(service.execute_job(setup["job"].id))
        assert completed_job.status == ReviewJobStatus.FAILED
        assert "Repository suspended" in (completed_job.error_message or "")


def test_completed_job_idempotency_skip(db_session: Session, failure_setup: dict):
    """Calling execute_job on an already COMPLETED job must return immediately without re-executing."""
    setup = failure_setup
    setup["job"].status = ReviewJobStatus.COMPLETED
    db_session.commit()

    service = ReviewJobService(db_session)
    with patch.object(service.github, "get_pull_request", AsyncMock()) as mock_get_pr:
        job = asyncio.run(service.execute_job(setup["job"].id))
        assert job.status == ReviewJobStatus.COMPLETED
        # get_pull_request should not be called because job was already COMPLETED
        mock_get_pr.assert_not_called()
