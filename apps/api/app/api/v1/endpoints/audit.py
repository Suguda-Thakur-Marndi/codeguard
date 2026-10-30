"""Audit trail REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass, verify_tenant_access
from app.db.session import get_db
from app.models.repository import Repository
from app.models.tool_audit import ToolExecutionAudit

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=dict[str, Any])
def list_audit_events(
    organization_id: str | None = Query(default=None),
    repository_id: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    import math

    from sqlalchemy import func

    user_org_id = _user.get("organization_id")
    effective_org_id = organization_id
    if user_org_id:
        verify_tenant_access(_user, organization_id, db=db)
        effective_org_id = user_org_id
    else:
        verify_tenant_access(_user, organization_id, db=db)

    if repository_id and effective_org_id:
        repo = db.scalar(select(Repository).where(Repository.id == repository_id))
        if repo and repo.organization_id != effective_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant access forbidden",
            )

    query = select(ToolExecutionAudit).order_by(ToolExecutionAudit.created_at.desc())
    count_query = select(func.count(ToolExecutionAudit.id))
    if effective_org_id:
        query = query.where(ToolExecutionAudit.organization_id == effective_org_id)
        count_query = count_query.where(ToolExecutionAudit.organization_id == effective_org_id)
    if repository_id:
        query = query.where(ToolExecutionAudit.repository_id == repository_id)
        count_query = count_query.where(ToolExecutionAudit.repository_id == repository_id)
    if tool_name:
        query = query.where(ToolExecutionAudit.tool_name == tool_name)
        count_query = count_query.where(ToolExecutionAudit.tool_name == tool_name)

    effective_page = page or 1
    effective_limit = page_size if page_size is not None else limit
    effective_offset = (effective_page - 1) * effective_limit if page is not None else offset

    total = db.scalar(count_query) or 0
    total_pages = math.ceil(total / effective_limit) if total > 0 else 1
    items = list(db.scalars(query.offset(effective_offset).limit(effective_limit)).all())
    return {
        "items": [
            {
                "id": a.id,
                "principal_id": a.principal_id,
                "organization_id": a.organization_id,
                "repository_id": a.repository_id,
                "tool_name": a.tool_name,
                "resource_type": a.resource_type,
                "resource_id": a.resource_id,
                "risk_level": a.risk_level,
                "authorization_decision": a.authorization_decision,
                "approval_id": a.approval_id,
                "execution_status": a.execution_status,
                "started_at": a.started_at.isoformat(),
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                "duration_ms": a.duration_ms,
                "error_code": a.error_code,
                "created_at": a.created_at.isoformat(),
            }
            for a in items
        ],
        "total": total,
        "page": effective_page,
        "page_size": effective_limit,
        "total_pages": total_pages,
    }


@router.get("/review-jobs/{review_job_id}/audit", response_model=dict[str, Any])
def get_job_audit_trail(
    review_job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    # Query audit logs relating to this review job
    query = (
        select(ToolExecutionAudit)
        .where(ToolExecutionAudit.resource_id == review_job_id)
        .order_by(ToolExecutionAudit.created_at.desc())
    )
    items = list(db.scalars(query).all())
    return {
        "items": [
            {
                "id": a.id,
                "principal_id": a.principal_id,
                "tool_name": a.tool_name,
                "risk_level": a.risk_level,
                "authorization_decision": a.authorization_decision,
                "approval_id": a.approval_id,
                "execution_status": a.execution_status,
                "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat(),
            }
            for a in items
        ],
        "total": len(items),
    }
