"""Pull Requests API endpoints."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass, verify_tenant_access
from app.db.repositories.pull_request_repo import PullRequestRepository
from app.db.repositories.repository_repo import RepositoryRepository
from app.db.repositories.review_job_repo import ReviewJobRepository
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.pull_request import PullRequestDetail, PullRequestRead
from app.schemas.review_job import ReviewJobRead

router = APIRouter(prefix="/pull-requests", tags=["Pull Requests"])


@router.get("", response_model=PaginatedResponse[PullRequestRead])
def list_pull_requests(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    repository_id: str | None = Query(None, description="Filter by repository ID"),
    state: str | None = Query(None, description="Filter by PR state ('open', 'closed')"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> PaginatedResponse[PullRequestRead]:
    """List pull requests with pagination, state filters, and tenant isolation."""
    user_org_id = _user.get("organization_id")

    if repository_id and user_org_id:
        target_repo = RepositoryRepository(db).get_by_id(repository_id)
        if target_repo:
            verify_tenant_access(_user, target_repo.organization_id)

    repo = PullRequestRepository(db)
    items, total = repo.list_pull_requests(
        page=page,
        page_size=page_size,
        repository_id=repository_id,
        state=state,
        organization_id=user_org_id,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse[PullRequestRead](
        items=[PullRequestRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{pull_request_id}", response_model=PullRequestDetail)
def get_pull_request(
    pull_request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> PullRequestDetail:
    """Retrieve pull request details with repository information and latest review status."""
    pr_repo = PullRequestRepository(db)
    pr = pr_repo.get_by_id(pull_request_id)
    if not pr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pull request with ID '{pull_request_id}' not found",
        )
    verify_tenant_access(_user, pr.repository.organization_id)

    # Attach latest review status if any jobs exist
    latest_review_status = None
    if pr.review_jobs:
        latest_review_status = pr.review_jobs[0].status.value

    detail = PullRequestDetail.model_validate(pr)
    detail.latest_review_status = latest_review_status
    return detail


@router.get("/{pull_request_id}/reviews", response_model=PaginatedResponse[ReviewJobRead])
def get_pull_request_reviews(
    pull_request_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> PaginatedResponse[ReviewJobRead]:
    """List all review jobs associated with this pull request."""
    pr_repo = PullRequestRepository(db)
    pr = pr_repo.get_by_id(pull_request_id)
    if not pr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pull request with ID '{pull_request_id}' not found",
        )
    verify_tenant_access(_user, pr.repository.organization_id)

    job_repo = ReviewJobRepository(db)
    items, total = job_repo.list_by_pull_request(
        pull_request_id=pull_request_id, page=page, page_size=page_size
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse[ReviewJobRead](
        items=[ReviewJobRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
