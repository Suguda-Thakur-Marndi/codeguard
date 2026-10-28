"""Repositories API endpoints."""

import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass, verify_tenant_access
from app.db.repositories.repository_repo import RepositoryRepository
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.repository import RepositoryDetail, RepositoryRead

router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.get("", response_model=PaginatedResponse[RepositoryRead])
def list_repositories(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    organization_id: str | None = Query(None, description="Filter by organization ID"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> PaginatedResponse[RepositoryRead]:
    """List connected repositories with pagination and tenant isolation."""
    user_org_id = _user.get("organization_id")
    effective_org_id = organization_id
    if user_org_id:
        verify_tenant_access(_user, organization_id)
        effective_org_id = user_org_id

    repo = RepositoryRepository(db)
    items, total = repo.list_repositories(
        page=page, page_size=page_size, organization_id=effective_org_id
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse[RepositoryRead](
        items=[RepositoryRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{repository_id}", response_model=RepositoryDetail)
def get_repository(
    repository_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> RepositoryDetail:
    """Retrieve repository details by ID with tenant verification."""
    repo = RepositoryRepository(db)
    repository = repo.get_by_id(repository_id)
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID '{repository_id}' not found",
        )
    verify_tenant_access(_user, repository.organization_id)
    return RepositoryDetail.model_validate(repository)


@router.delete("/{repository_id}", status_code=status.HTTP_200_OK)
def delete_repository(
    repository_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    """Disconnect repository from CodeGuard with tenant verification."""
    repo = RepositoryRepository(db)
    repository = repo.get_by_id(repository_id)
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID '{repository_id}' not found",
        )
    verify_tenant_access(_user, repository.organization_id)
    repo.delete(repository)
    return {
        "success": True,
        "message": f"Repository '{repository.full_name}' disconnected successfully",
        "repository_id": repository_id,
    }
