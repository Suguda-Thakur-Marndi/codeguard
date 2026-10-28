"""Regression test suite for real repository code ingestion and ephemeral workspace isolation.

Verifies:
1. Real repositories do not accidentally analyze or index local fixture code.
2. Ephemeral workspace directories are completely cleaned up on success and failure.
3. Path traversal (Tar Slip) attempts are detected, rejected, and sanitized.
4. Resource exhaustion (decompression limits) triggers safe rejection.
5. In production mode, silent fallback to fixtures is strictly prevented.
6. Explicit test fixture repositories remain usable when intentionally targeted.
"""

import io
import os
import tarfile
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import GitHubAPIError
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review_job import ReviewJob, ReviewJobStatus
from app.services.ephemeral_workspace import (
    EphemeralWorkspace,
    ResourceExhaustionError,
    SecurityArchiveError,
)
from app.services.review_job_service import MockLLMProvider, ReviewJobService


@pytest.fixture
def real_repo_job(db_session: Session) -> Generator[ReviewJob, None, None]:
    """Create a test review job for a real third-party repository."""
    org = Organization(
        github_installation_id=778899,
        github_account_id=1122,
        github_account_login="acme-corp",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=556677,
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
        github_pr_id=334455,
        number=101,
        title="Update payment notification handler",
        description="Refactors webhook notifications.",
        author_login="octocat",
        base_sha="1111111111111111111111111111111111111111",
        head_sha="2222222222222222222222222222222222222222",
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

    yield job


@pytest.mark.asyncio
async def test_real_repo_does_not_index_fixture_files(
    db_session: Session, real_repo_job: ReviewJob
) -> None:
    """Real repository review must acquire its own code and NEVER index fixtures/python_repo."""
    service = ReviewJobService(db_session)

    job = await service.execute_job(real_repo_job.id)
    assert job.status == ReviewJobStatus.COMPLETED

    # Query all indexed symbols for this real repository
    symbols, total = service.ci_service.symbol_repo.list_symbols(
        repository_id=job.pull_request.repository_id,
        commit_sha=job.pull_request.head_sha,
    )
    symbol_names = {s.name for s in symbols}

    # Verify that symbols from fixtures/python_repo are NOT present!
    assert "PaymentService.refund" not in symbol_names
    assert "RefundController" not in symbol_names
    assert "AuthService" not in symbol_names
    assert "PaymentRepository" not in symbol_names

    # Verify that the mock code from GitHub archive was indexed instead
    assert "hello" in symbol_names


@pytest.mark.asyncio
async def test_ephemeral_workspace_cleaned_up_after_execution(
    db_session: Session, real_repo_job: ReviewJob
) -> None:
    """Ephemeral directories must be deleted from disk on job completion."""
    service = ReviewJobService(db_session)

    # Track directory paths created by EphemeralWorkspace
    created_dirs: list[str] = []
    original_init = EphemeralWorkspace.__init__

    def intercept_init(self, prefix: str = "codeguard_repo_"):
        original_init(self, prefix=prefix)
        created_dirs.append(self.temp_dir)

    EphemeralWorkspace.__init__ = intercept_init  # type: ignore[method-assign]
    try:
        job = await service.execute_job(real_repo_job.id)
        assert job.status == ReviewJobStatus.COMPLETED
        assert len(created_dirs) > 0

        # Verify that all created temporary directories have been cleaned up
        for temp_path in created_dirs:
            assert not os.path.exists(temp_path), f"Temporary directory {temp_path} was not cleaned up!"
    finally:
        EphemeralWorkspace.__init__ = original_init  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_ephemeral_workspace_cleaned_up_on_failure(
    db_session: Session, real_repo_job: ReviewJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ephemeral directories must be deleted from disk even when review fails downstream."""
    service = ReviewJobService(db_session)

    # Force downstream engine failure
    def mock_fail_analysis(*args, **kwargs):
        raise RuntimeError("Simulated AST parsing crash")

    monkeypatch.setattr(service.engine, "analyze_pull_request", mock_fail_analysis)

    created_dirs: list[str] = []
    original_init = EphemeralWorkspace.__init__

    def intercept_init(self, prefix: str = "codeguard_repo_"):
        original_init(self, prefix=prefix)
        created_dirs.append(self.temp_dir)

    EphemeralWorkspace.__init__ = intercept_init  # type: ignore[method-assign]
    try:
        job = await service.execute_job(real_repo_job.id)
        assert job.status == ReviewJobStatus.FAILED
        assert len(created_dirs) > 0

        for temp_path in created_dirs:
            assert not os.path.exists(temp_path), f"Temporary directory {temp_path} lingered after failure!"
    finally:
        EphemeralWorkspace.__init__ = original_init  # type: ignore[method-assign]


def test_ephemeral_workspace_tar_slip_rejection() -> None:
    """Attempting to extract an archive with path traversal ('..') must be rejected."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = b"print('malicious file escape')"
        ti = tarfile.TarInfo(name="../evil_escape.py")
        ti.size = len(payload)
        tar.addfile(ti, io.BytesIO(payload))

    workspace = EphemeralWorkspace()
    try:
        with pytest.raises(SecurityArchiveError) as exc_info:
            workspace.extract_tarball(buf.getvalue())
        assert "escapes base directory" in str(exc_info.value)
    finally:
        workspace.cleanup()
        assert not os.path.exists(workspace.temp_dir)


def test_ephemeral_workspace_resource_exhaustion() -> None:
    """Attempting to extract an archive exceeding member size limit must be rejected."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"x" * 200
        ti = tarfile.TarInfo(name="repo/large_file.dat")
        ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))

    workspace = EphemeralWorkspace()
    workspace.MAX_SINGLE_FILE_BYTES = 100
    try:
        with pytest.raises(ResourceExhaustionError) as exc_info:
            workspace.extract_tarball(buf.getvalue())
        assert "exceeds limit" in str(exc_info.value)
    finally:
        workspace.cleanup()
        assert not os.path.exists(workspace.temp_dir)


def test_ephemeral_workspace_file_count_exhaustion() -> None:
    """Attempting to extract an archive exceeding maximum file count must be rejected."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for i in range(10):
            data = b"x"
            ti = tarfile.TarInfo(name=f"repo/file_{i}.txt")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

    workspace = EphemeralWorkspace()
    workspace.MAX_FILE_COUNT = 5
    try:
        with pytest.raises(ResourceExhaustionError) as exc_info:
            workspace.extract_tarball(buf.getvalue())
        assert "too many files" in str(exc_info.value)
    finally:
        workspace.cleanup()
        assert not os.path.exists(workspace.temp_dir)


@pytest.mark.asyncio
async def test_production_environment_prevents_silent_fallback(
    db_session: Session, real_repo_job: ReviewJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In production mode, archive failure must raise GitHubAPIError and never fall back to fixtures."""
    monkeypatch.setattr(settings, "APP_ENV", "production")

    service = ReviewJobService(db_session, llm_provider=MockLLMProvider())

    # Simulate GitHub archive download error
    async def mock_download_error(*args, **kwargs):
        raise GitHubAPIError("GitHub 502 Bad Gateway while fetching tarball", status_code=502)

    monkeypatch.setattr(service.github, "download_repository_archive", mock_download_error)

    with pytest.raises(GitHubAPIError) as exc_info:
        await service._acquire_source_provider(
            repo=real_repo_job.pull_request.repository,
            head_sha=real_repo_job.pull_request.head_sha,
            installation_id=1,
            raw_diff="diff --git a/test.py b/test.py",
        )
    assert "Failed to acquire repository source archive" in str(exc_info.value)


@pytest.mark.asyncio
async def test_real_repo_uses_exact_head_commit_sha(
    db_session: Session, real_repo_job: ReviewJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real PR reviews must request the exact head commit SHA, not default branch."""
    service = ReviewJobService(db_session)
    requested_refs: list[str] = []

    original_download = service.github.download_repository_archive

    async def mock_download(owner, repo, ref, installation_id=None, max_size_bytes=50 * 1024 * 1024):
        requested_refs.append(ref)
        return await original_download(owner, repo, ref, installation_id=installation_id, max_size_bytes=max_size_bytes)

    monkeypatch.setattr(service.github, "download_repository_archive", mock_download)

    job = await service.execute_job(real_repo_job.id)
    assert job.status == ReviewJobStatus.COMPLETED
    assert requested_refs == [real_repo_job.pull_request.head_sha]
    assert real_repo_job.pull_request.repository.default_branch not in requested_refs


@pytest.mark.asyncio
async def test_missing_or_inaccessible_source_causes_clear_failure(
    db_session: Session, real_repo_job: ReviewJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When repository source is missing or inaccessible from GitHub, job must fail clearly with no fixture fallback."""
    service = ReviewJobService(db_session)

    async def mock_download_404(*args, **kwargs):
        from app.core.exceptions import GitHubNotFoundError
        raise GitHubNotFoundError("Repository archive for acme-corp/payment-service at 222222 not found")

    monkeypatch.setattr(service.github, "download_repository_archive", mock_download_404)

    job = await service.execute_job(real_repo_job.id)
    assert job.status == ReviewJobStatus.FAILED
    assert "Failed to acquire repository source archive" in (job.error_message or "")

    # Ensure no symbols from fixtures were indexed
    symbols, total = service.ci_service.symbol_repo.list_symbols(
        repository_id=real_repo_job.pull_request.repository_id,
        commit_sha=real_repo_job.pull_request.head_sha,
    )
    assert total == 0


@pytest.mark.asyncio
async def test_duplicate_job_protection_intact(
    db_session: Session, real_repo_job: ReviewJob
) -> None:
    """Executing an already completed job returns the existing completed job without re-executing."""
    service = ReviewJobService(db_session)

    job1 = await service.execute_job(real_repo_job.id)
    assert job1.status == ReviewJobStatus.COMPLETED

    # Second execution attempt should be idempotent
    job2 = await service.execute_job(real_repo_job.id)
    assert job2.status == ReviewJobStatus.COMPLETED
    assert job2.id == job1.id


@pytest.mark.asyncio
async def test_explicit_fixture_repo_allowed_for_dev_test(
    db_session: Session
) -> None:
    """Fixtures remain available for tests and explicitly configured local development."""
    org = Organization(
        github_installation_id=999111,
        github_account_id=999222,
        github_account_login="fixtures",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=999333,
        owner="fixtures",
        name="python_repo",
        full_name="fixtures/python_repo",
        default_branch="main",
        is_private=False,
    )
    db_session.add(repo)
    db_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=999444,
        number=1,
        title="Fixture PR",
        author_login="tester",
        base_sha="0000000000000000000000000000000000000000",
        head_sha="ffffffffffffffffffffffffffffffffffffffff",
        state="open",
        is_draft=False,
    )
    db_session.add(pr)
    db_session.flush()

    service = ReviewJobService(db_session)
    provider, cleanup = await service._acquire_source_provider(
        repo=repo,
        head_sha=pr.head_sha,
        installation_id=org.github_installation_id,
        raw_diff="diff --git a/test.py b/test.py",
    )
    # Explicit fixture repos resolve to LocalDiskRepositorySourceProvider without cleanup callback
    assert cleanup is None
    assert hasattr(provider, "root_dir")
    assert "fixtures" in provider.root_dir or "python_repo" in provider.root_dir

