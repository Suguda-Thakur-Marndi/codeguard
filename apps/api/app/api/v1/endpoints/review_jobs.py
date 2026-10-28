import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass, verify_tenant_access
from app.db.repositories.review_artifact_repo import ReviewArtifactRepository
from app.db.repositories.review_finding_repo import ReviewFindingRepository
from app.db.repositories.review_job_repo import ReviewJobRepository
from app.db.session import get_db
from app.models.review_artifact import ArtifactType
from app.models.review_job import ReviewJob
from app.schemas.code_intelligence import (
    ASTChunkSchema,
    ChangedLineIndexSchema,
    DiffFileSchema,
)
from app.schemas.review_artifact import ReviewArtifactRead
from app.schemas.review_finding import (
    AgentRunRead,
    AgentTraceRead,
    ReviewFindingRead,
    ReviewUsageRead,
)
from app.schemas.review_job import ReviewJobRead
from app.schemas.verification import (
    JudgeRunRead,
    ValidationScenarioRead,
    VerificationSummaryRead,
)
from app.services.review_job_service import ReviewJobService

router = APIRouter(prefix="/review-jobs", tags=["Review Jobs"])


def _get_verified_job(job_id: str, db: Session, user: dict) -> ReviewJob:
    """Retrieve review job and enforce tenant authorization."""
    repo = ReviewJobRepository(db)
    job = repo.get_by_id(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review job with ID '{job_id}' not found",
        )
    verify_tenant_access(user, job.pull_request.repository.organization_id)
    return job


@router.get("/{job_id}", response_model=ReviewJobRead)
def get_review_job(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> ReviewJobRead:
    """Retrieve review job details and status with tenant isolation."""
    job = _get_verified_job(job_id, db, _user)
    return ReviewJobRead.model_validate(job)


@router.get("/{job_id}/artifacts", response_model=list[ReviewArtifactRead])
def get_review_job_artifacts(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[ReviewArtifactRead]:
    """Retrieve all artifacts (PR_METADATA, DIFF) generated for a review job."""
    _get_verified_job(job_id, db, _user)
    artifact_repo = ReviewArtifactRepository(db)
    artifacts = artifact_repo.list_by_review_job(job_id)
    return [ReviewArtifactRead.model_validate(a) for a in artifacts]


@router.get("/{job_id}/diff", response_model=list[DiffFileSchema])
def get_review_job_diff(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[DiffFileSchema]:
    """Retrieve parsed unified diff files and hunks for a review job."""
    _get_verified_job(job_id, db, _user)
    artifact_repo = ReviewArtifactRepository(db)
    artifact = artifact_repo.get_by_job_and_type(job_id, ArtifactType.PARSED_DIFF)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parsed diff artifact not found for review job '{job_id}'",
        )
    data = json.loads(artifact.content)
    return [DiffFileSchema.model_validate(f) for f in data]


@router.get("/{job_id}/chunks", response_model=list[ASTChunkSchema])
def get_review_job_chunks(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[ASTChunkSchema]:
    """Retrieve AST semantic chunks covering changed lines for a review job."""
    _get_verified_job(job_id, db, _user)
    artifact_repo = ReviewArtifactRepository(db)
    artifact = artifact_repo.get_by_job_and_type(job_id, ArtifactType.AST_CHUNKS)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AST chunks artifact not found for review job '{job_id}'",
        )
    data = json.loads(artifact.content)
    return [ASTChunkSchema.model_validate(c) for c in data]


@router.get("/{job_id}/changed-lines", response_model=ChangedLineIndexSchema)
def get_review_job_changed_lines(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> ChangedLineIndexSchema:
    """Retrieve deterministic changed line index (LEFT vs RIGHT) for a review job."""
    _get_verified_job(job_id, db, _user)
    artifact_repo = ReviewArtifactRepository(db)
    artifact = artifact_repo.get_by_job_and_type(job_id, ArtifactType.CHANGED_LINE_INDEX)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Changed line index artifact not found for review job '{job_id}'",
        )
    data = json.loads(artifact.content)
    return ChangedLineIndexSchema(index=data)


# -------------------------------------------------------------------------
# Phase 3: AI Agent Review Engine Endpoints
# -------------------------------------------------------------------------
@router.get("/{job_id}/agents", response_model=list[AgentRunRead])
def get_review_job_agents(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[AgentRunRead]:
    """Retrieve execution records for all specialist agents run on this job."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    runs = finding_repo.list_agent_runs(job_id)
    return [AgentRunRead.model_validate(r) for r in runs]


@router.get("/{job_id}/findings", response_model=list[ReviewFindingRead])
def get_review_job_findings(
    job_id: str,
    severity: str | None = None,
    category: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[ReviewFindingRead]:
    """Retrieve candidate and validated code review findings."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    findings = finding_repo.list_findings(
        review_job_id=job_id,
        severity=severity,
        category=category,
        status=status_filter,
    )
    return [ReviewFindingRead.model_validate(f) for f in findings]


@router.get("/{job_id}/findings/{finding_id}", response_model=ReviewFindingRead)
def get_review_job_finding(
    job_id: str,
    finding_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> ReviewFindingRead:
    """Retrieve a specific finding by ID with full grounding evidence."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    finding = finding_repo.get_finding(finding_id)
    if not finding or finding.review_job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found for review job '{job_id}'",
        )
    return ReviewFindingRead.model_validate(finding)


@router.get("/{job_id}/trace", response_model=list[AgentTraceRead])
def get_review_job_trace(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[AgentTraceRead]:
    """Retrieve operational execution traces and latency metrics for all graph nodes."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    traces = finding_repo.list_agent_traces(job_id)
    return [AgentTraceRead.model_validate(t) for t in traces]


@router.get("/{job_id}/usage", response_model=ReviewUsageRead)
def get_review_job_usage(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> ReviewUsageRead:
    """Retrieve aggregated token usage, cost accounting, and latency breakdown."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    summary = finding_repo.get_job_usage_summary(job_id)
    return ReviewUsageRead.model_validate(summary)


@router.post("/{job_id}/rerun", response_model=ReviewJobRead)
async def rerun_review_job(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> ReviewJobRead:
    """Trigger a re-execution of the review job without deleting historical artifacts."""
    _get_verified_job(job_id, db, _user)
    service = ReviewJobService(db)
    updated_job = await service.rerun_job(job_id)
    return ReviewJobRead.model_validate(updated_job)


# -------------------------------------------------------------------------
# Phase 4: Adversarial Verification & Validation Endpoints
# -------------------------------------------------------------------------
@router.get("/{job_id}/verification", response_model=VerificationSummaryRead)
def get_review_job_verification_summary(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> VerificationSummaryRead:
    """Retrieve high-level verification summary (candidate, verified, rejected counts)."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    summary = finding_repo.get_job_verification_summary(job_id)
    return VerificationSummaryRead.model_validate(summary)


@router.get("/{job_id}/judge", response_model=list[JudgeRunRead])
def get_review_job_judge_runs(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[JudgeRunRead]:
    """Retrieve all Adversarial Judge runs and decisions for this review job."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    runs = finding_repo.list_judge_runs(job_id)
    return [JudgeRunRead.model_validate(r) for r in runs]


@router.get("/{job_id}/validation", response_model=list[ValidationScenarioRead])
def get_review_job_validation_scenarios(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[ValidationScenarioRead]:
    """Retrieve all validation scenarios (sandbox and static) and results for this review job."""
    _get_verified_job(job_id, db, _user)
    finding_repo = ReviewFindingRepository(db)
    scenarios = finding_repo.list_validation_scenarios_for_job(job_id)
    return [ValidationScenarioRead.model_validate(s) for s in scenarios]
    finding_repo = ReviewFindingRepository(db)
    scenarios = finding_repo.list_validation_scenarios_for_job(job_id)
    return [ValidationScenarioRead.model_validate(s) for s in scenarios]


