"""API router for individual finding operations and verification actions."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass, verify_tenant_access
from app.db.repositories.review_finding_repo import ReviewFindingRepository
from app.db.session import get_db
from app.models.review_finding import ReviewFindingModel
from app.schemas.verification import (
    FindingDetailRead,
    FindingEvidenceRead,
    VerificationEventRead,
)

router = APIRouter(prefix="/findings", tags=["Findings"])


def _get_verified_finding(
    finding_id: str, repo: ReviewFindingRepository, user: dict
) -> ReviewFindingModel:
    """Retrieve finding and enforce tenant isolation."""
    finding = repo.get_finding(finding_id)
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found",
        )
    if finding.review_job and finding.review_job.pull_request and finding.review_job.pull_request.repository:
        verify_tenant_access(user, finding.review_job.pull_request.repository.organization_id, db=repo.db)
    return finding


@router.get("/{finding_id}", response_model=FindingDetailRead)
def get_finding_detail(
    finding_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> FindingDetailRead:
    """Retrieve finding details with full judge decisions, validation scenarios, and evidence."""
    repo = ReviewFindingRepository(db)
    finding = _get_verified_finding(finding_id, repo, _user)
    return FindingDetailRead.model_validate(finding)


@router.get("/{finding_id}/evidence", response_model=list[FindingEvidenceRead])
def get_finding_evidence(
    finding_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[FindingEvidenceRead]:
    """Retrieve immutable grounding evidence chain for a finding."""
    repo = ReviewFindingRepository(db)
    _get_verified_finding(finding_id, repo, _user)
    items = repo.list_evidence_for_finding(finding_id)
    return [FindingEvidenceRead.model_validate(item) for item in items]


@router.get("/{finding_id}/history", response_model=list[VerificationEventRead])
def get_finding_history(
    finding_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> list[VerificationEventRead]:
    """Retrieve immutable audit trail history for a finding."""
    repo = ReviewFindingRepository(db)
    _get_verified_finding(finding_id, repo, _user)
    events = repo.list_events_for_finding(finding_id)
    return [VerificationEventRead.model_validate(ev) for ev in events]


@router.post("/{finding_id}/verify", response_model=FindingDetailRead)
async def verify_finding_endpoint(
    finding_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> FindingDetailRead:
    """Trigger ad-hoc adversarial judge verification for a specific finding."""
    repo = ReviewFindingRepository(db)
    finding = repo.get_finding(finding_id)
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found",
        )

    # Record event
    repo.record_verification_event(
        review_job_id=finding.review_job_id,
        finding_id=finding.id,
        event_type="adhoc_verification_triggered",
    )

    # Re-fetch and return
    refreshed = repo.get_finding(finding_id)
    return FindingDetailRead.model_validate(refreshed)


@router.post("/{finding_id}/rerun-validation", response_model=FindingDetailRead)
async def rerun_finding_validation_endpoint(
    finding_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> FindingDetailRead:
    """Re-execute validation scenarios (sandbox or static) for a specific finding."""
    repo = ReviewFindingRepository(db)
    finding = repo.get_finding(finding_id)
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found",
        )

    repo.record_verification_event(
        review_job_id=finding.review_job_id,
        finding_id=finding.id,
        event_type="adhoc_validation_triggered",
    )

    refreshed = repo.get_finding(finding_id)
    return FindingDetailRead.model_validate(refreshed)
