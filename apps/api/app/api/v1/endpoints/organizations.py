"""Organizations API endpoints."""

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user_or_bypass
from app.db.repositories.organization_repo import OrganizationRepository
from app.db.session import get_db
from app.models.membership import MembershipStatus, UserOrganizationMembership
from app.models.organization import Organization
from app.schemas.common import PaginatedResponse
from app.schemas.organization import OrganizationRead

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get("", response_model=PaginatedResponse[OrganizationRead])
def list_organizations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> PaginatedResponse[OrganizationRead]:
    """List installed organizations with pagination and tenant filtering."""
    repo = OrganizationRepository(db)

    is_dev = bool(
        _user.get("is_dev")
        and settings.DEV_AUTH_BYPASS
        and settings.APP_ENV in ("development", "test")
    )

    if _user.get("role") == "system" or (is_dev and not _user.get("organization_id")):
        items, total = repo.get_all(page=page, page_size=page_size)
    else:
        # Determine allowed organizations for the current principal
        allowed_org_ids: list[str] = []
        user_id = _user.get("id")
        if user_id:
            memberships = (
                db.query(UserOrganizationMembership)
                .filter(
                    UserOrganizationMembership.user_id == user_id,
                    UserOrganizationMembership.status == MembershipStatus.ACTIVE.value,
                )
                .all()
            )
            allowed_org_ids = [m.organization_id for m in memberships]

        if not allowed_org_ids and _user.get("organizations"):
            allowed_org_ids = [str(o) for o in _user["organizations"]]
        if not allowed_org_ids and _user.get("organization_id"):
            allowed_org_ids = [str(_user["organization_id"])]

        if not allowed_org_ids:
            items, total = [], 0
        else:
            stmt = (
                select(Organization)
                .where(Organization.id.in_(allowed_org_ids))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = list(db.execute(stmt).scalars().all())
            total = (
                db.query(Organization)
                .filter(Organization.id.in_(allowed_org_ids))
                .count()
            )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse[OrganizationRead](
        items=[OrganizationRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
