"""Publication REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass
from app.db.session import get_db
from app.models.github_publication import GitHubReviewPublication, PublicationStatus
from app.services.publication_service import PublicationService
from app.workers.tasks import publish_review_sync

router = APIRouter(tags=["publications"])


class PublishRequestPayload(BaseModel):
    action: str = "COMMENT"


@router.get("/review-jobs/{review_job_id}/publication", response_model=dict[str, Any])
def get_job_publication(
    review_job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    pub = db.scalar(
        select(GitHubReviewPublication)
        .where(GitHubReviewPublication.review_job_id == review_job_id)
        .order_by(GitHubReviewPublication.created_at.desc())
    )
    if not pub:
        return {"publication": None}

    user_org_id = _user.get("organization_id")
    if user_org_id:
        from app.models.repository import Repository

        repo = db.scalar(select(Repository).where(Repository.id == pub.repository_id))
        if repo and repo.organization_id != user_org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access forbidden")

    comments = [
        {
            "id": c.id,
            "github_comment_id": c.github_comment_id,
            "file_path": c.file_path,
            "line_number": c.line_number,
            "side": c.side,
            "status": c.status,
        }
        for c in pub.comments
    ]

    return {
        "publication": {
            "id": pub.id,
            "review_job_id": pub.review_job_id,
            "repository_id": pub.repository_id,
            "pull_request_id": pub.pull_request_id,
            "head_sha": pub.head_sha,
            "github_review_id": pub.github_review_id,
            "event": pub.event,
            "status": pub.status.value,
            "comment_count": pub.comment_count,
            "published_at": pub.published_at.isoformat() if pub.published_at else None,
            "error_message": pub.error_message,
            "comments": comments,
        }
    }


@router.post("/review-jobs/{review_job_id}/publish", response_model=dict[str, Any])
@router.post("/review-jobs/{review_job_id}/publication/publish", response_model=dict[str, Any])
def publish_job_review(
    review_job_id: str,
    payload: PublishRequestPayload = PublishRequestPayload(),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    user_org_id = _user.get("organization_id")
    if user_org_id:
        from app.models.pull_request import PullRequest
        from app.models.repository import Repository
        from app.models.review_job import ReviewJob

        job = db.scalar(select(ReviewJob).where(ReviewJob.id == review_job_id))
        if job:
            pr = db.scalar(select(PullRequest).where(PullRequest.id == job.pull_request_id))
            if pr:
                repo = db.scalar(select(Repository).where(Repository.id == pr.repository_id))
                if repo and repo.organization_id != user_org_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access forbidden")

    service = PublicationService(db)
    try:
        pub, approval_req = service.prepare_publication(
            review_job_id=review_job_id,
            action=payload.action,
        )

        if pub.status == PublicationStatus.APPROVAL_REQUIRED:
            return {
                "status": "APPROVAL_REQUIRED",
                "publication_id": pub.id,
                "approval_id": approval_req.id if approval_req else None,
                "message": "Action requires human approval before publishing.",
            }

        if pub.status == PublicationStatus.PUBLISHED:
            return {
                "status": "ALREADY_PUBLISHED",
                "publication_id": pub.id,
                "github_review_id": pub.github_review_id,
                "message": "Review is already published (idempotent).",
            }

        # Ready to publish: run sync or dispatch worker
        res = publish_review_sync(publication_id=pub.id, db=db)
        return {
            "status": res["publication_status"],
            "publication_id": pub.id,
            "github_review_id": res.get("github_review_id"),
        }

    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


class ApprovalRequestPayload(BaseModel):
    finding_id: str | None = None
    action: str = "COMMENT"


@router.post("/review-jobs/{review_job_id}/publication/request-approval", response_model=dict[str, Any])
def request_job_approval(
    review_job_id: str,
    payload: ApprovalRequestPayload = ApprovalRequestPayload(),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    user_org_id = _user.get("organization_id")
    if user_org_id:
        from app.models.pull_request import PullRequest
        from app.models.repository import Repository
        from app.models.review_job import ReviewJob

        job = db.scalar(select(ReviewJob).where(ReviewJob.id == review_job_id))
        if job:
            pr = db.scalar(select(PullRequest).where(PullRequest.id == job.pull_request_id))
            if pr:
                repo = db.scalar(select(Repository).where(Repository.id == pr.repository_id))
                if repo and repo.organization_id != user_org_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access forbidden")

    service = PublicationService(db)
    try:
        pub, approval_req = service.prepare_publication(
            review_job_id=review_job_id,
            action=payload.action,
        )
        return {
            "approval_id": approval_req.id if approval_req else None,
            "publication_id": pub.id,
            "status": "PENDING" if approval_req else pub.status.value,
            "message": "Approval request registered in governance log." if approval_req else "Publication authorized.",
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

