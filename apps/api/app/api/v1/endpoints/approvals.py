"""Approval request REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass
from app.db.session import get_db
from app.models.approval_request import ApprovalStatus
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovePayload(BaseModel):
    comment: str | None = None


class RejectPayload(BaseModel):
    reason: str


@router.get("", response_model=dict[str, Any])
def list_approvals(
    organization_id: str | None = Query(default=None),
    repository_id: str | None = Query(default=None),
    pull_request_id: str | None = Query(default=None),
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    import math

    user_org_id = _user.get("organization_id")
    effective_org_id = organization_id
    if user_org_id:
        if organization_id and organization_id != user_org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access forbidden")
        effective_org_id = user_org_id

    effective_page = page or 1
    effective_limit = page_size if page_size is not None else limit
    effective_offset = (effective_page - 1) * effective_limit if page is not None else offset

    service = ApprovalService(db)
    items = service.list_approval_requests(
        organization_id=effective_org_id,
        repository_id=repository_id,
        pull_request_id=pull_request_id,
        status=status_filter,
        limit=effective_limit,
        offset=effective_offset,
    )
    total = service.count_approval_requests(
        organization_id=effective_org_id,
        repository_id=repository_id,
        pull_request_id=pull_request_id,
        status=status_filter,
    )
    total_pages = math.ceil(total / effective_limit) if total > 0 else 1

    return {
        "items": [
            {
                "id": req.id,
                "organization_id": req.organization_id,
                "repository_id": req.repository_id,
                "pull_request_id": req.pull_request_id,
                "review_job_id": req.review_job_id,
                "finding_id": req.finding_id,
                "requested_action": req.requested_action,
                "risk_level": req.risk_level,
                "status": req.status.value,
                "requested_by": req.requested_by,
                "approved_by": req.approved_by,
                "head_sha": req.head_sha,
                "expires_at": req.expires_at.isoformat(),
                "resolved_at": req.resolved_at.isoformat() if req.resolved_at else None,
                "reason": req.reason,
                "created_at": req.created_at.isoformat(),
            }
            for req in items
        ],
        "total": total,
        "page": effective_page,
        "page_size": effective_limit,
        "total_pages": total_pages,
    }


@router.get("/{approval_id}", response_model=dict[str, Any])
def get_approval(
    approval_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    service = ApprovalService(db)
    req = service.get_approval_request(approval_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")

    user_org_id = _user.get("organization_id")
    if user_org_id and req.organization_id != user_org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access forbidden")

    return {
        "id": req.id,
        "organization_id": req.organization_id,
        "repository_id": req.repository_id,
        "pull_request_id": req.pull_request_id,
        "review_job_id": req.review_job_id,
        "finding_id": req.finding_id,
        "requested_action": req.requested_action,
        "risk_level": req.risk_level,
        "status": req.status.value,
        "requested_by": req.requested_by,
        "approved_by": req.approved_by,
        "head_sha": req.head_sha,
        "expires_at": req.expires_at.isoformat(),
        "resolved_at": req.resolved_at.isoformat() if req.resolved_at else None,
        "reason": req.reason,
        "created_at": req.created_at.isoformat(),
    }


@router.post("/{approval_id}/approve", response_model=dict[str, Any])
def approve_request(
    approval_id: str,
    payload: ApprovePayload,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    service = ApprovalService(db)
    approver_principal_id = _user.get("id") or "human-reviewer"
    approver_role = str(_user.get("role", "REVIEWER")).upper()

    # In dev/test bypass mode or admin role, allow explicit header overrides
    if _user.get("is_dev") or _user.get("role") == "admin":
        if x_user_id:
            approver_principal_id = x_user_id
        if x_user_role:
            approver_role = x_user_role.upper()

    approver_org_id = _user.get("organization_id")
    try:
        req = service.approve_request(
            approval_id=approval_id,
            approver_principal_id=approver_principal_id,
            approver_role=approver_role,
            is_ai_agent=False,
            comment=payload.comment,
            approver_organization_id=approver_org_id,
        )

        # Transition associated publication from APPROVAL_REQUIRED to PENDING and trigger publication
        from sqlalchemy import select

        from app.models.github_publication import GitHubReviewPublication, PublicationStatus

        pub = db.scalar(
            select(GitHubReviewPublication).where(
                GitHubReviewPublication.review_job_id == req.review_job_id,
                GitHubReviewPublication.head_sha == req.head_sha,
                GitHubReviewPublication.status == PublicationStatus.APPROVAL_REQUIRED,
            )
        )
        if pub:
            pub.status = PublicationStatus.PENDING
            db.commit()
            try:
                from app.workers.tasks import publish_review_sync
                publish_review_sync(publication_id=pub.id, db=db)
            except Exception:
                pass

        return {
            "status": "success",
            "approval_id": req.id,
            "approval_status": req.status.value,
            "approved_by": req.approved_by,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{approval_id}/reject", response_model=dict[str, Any])
def reject_request(
    approval_id: str,
    payload: RejectPayload,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    service = ApprovalService(db)
    approver_principal_id = _user.get("id") or "human-reviewer"
    approver_role = str(_user.get("role", "REVIEWER")).upper()

    # In dev/test bypass mode or admin role, allow explicit header overrides
    if _user.get("is_dev") or _user.get("role") == "admin":
        if x_user_id:
            approver_principal_id = x_user_id
        if x_user_role:
            approver_role = x_user_role.upper()

    approver_org_id = _user.get("organization_id")
    try:
        req = service.reject_request(
            approval_id=approval_id,
            approver_principal_id=approver_principal_id,
            approver_role=approver_role,
            is_ai_agent=False,
            reason=payload.reason,
            approver_organization_id=approver_org_id,
        )

        from sqlalchemy import select

        from app.models.github_publication import GitHubReviewPublication, PublicationStatus

        pub = db.scalar(
            select(GitHubReviewPublication).where(
                GitHubReviewPublication.review_job_id == req.review_job_id,
                GitHubReviewPublication.head_sha == req.head_sha,
                GitHubReviewPublication.status == PublicationStatus.APPROVAL_REQUIRED,
            )
        )
        if pub:
            pub.status = PublicationStatus.FAILED
            pub.error_message = f"Publication rejected by reviewer: {payload.reason}"
            db.commit()

        return {
            "status": "success",
            "approval_id": req.id,
            "approval_status": req.status.value,
            "reason": req.reason,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
