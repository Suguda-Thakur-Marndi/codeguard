"""Organization review policies REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user_or_bypass, verify_tenant_access
from app.db.session import get_db
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/organizations", tags=["policies"])


class PolicyUpdatePayload(BaseModel):
    auto_publish_advisory: bool | None = None
    auto_publish_low: bool | None = None
    require_approval_for_high: bool | None = None
    require_approval_for_critical: bool | None = None
    allow_request_changes: bool | None = None
    allow_ai_github_comments: bool | None = None
    approval_expiry_minutes: int | None = None


@router.get("/{organization_id}/policies", response_model=dict[str, Any])
def get_organization_policies(
    organization_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    verify_tenant_access(_user, organization_id)
    service = PolicyService(db)
    policy = service.get_or_create_policy(organization_id)
    return {
        "policy": {
            "id": policy.id,
            "organization_id": policy.organization_id,
            "auto_publish_advisory": policy.auto_publish_advisory,
            "auto_publish_low": policy.auto_publish_low,
            "require_approval_for_high": policy.require_approval_for_high,
            "require_approval_for_critical": policy.require_approval_for_critical,
            "allow_request_changes": policy.allow_request_changes,
            "allow_ai_github_comments": policy.allow_ai_github_comments,
            "approval_expiry_minutes": policy.approval_expiry_minutes,
            "updated_at": policy.updated_at.isoformat(),
        }
    }


@router.patch("/{organization_id}/policies", response_model=dict[str, Any])
def update_organization_policies(
    organization_id: str,
    payload: PolicyUpdatePayload,
    x_user_role: str | None = Header(default=None),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    verify_tenant_access(_user, organization_id)
    service = PolicyService(db)
    user_role = str(_user.get("role", "MEMBER")).upper()
    if _user.get("is_dev") or user_role == "ADMIN":
        if x_user_role:
            user_role = x_user_role.upper()

    try:
        policy = service.update_policy(
            organization_id=organization_id,
            updater_role=user_role,
            updates=payload.model_dump(exclude_unset=True),
        )
        return {
            "status": "success",
            "policy": {
                "organization_id": policy.organization_id,
                "auto_publish_advisory": policy.auto_publish_advisory,
                "auto_publish_low": policy.auto_publish_low,
                "require_approval_for_high": policy.require_approval_for_high,
                "require_approval_for_critical": policy.require_approval_for_critical,
                "allow_request_changes": policy.allow_request_changes,
                "allow_ai_github_comments": policy.allow_ai_github_comments,
                "approval_expiry_minutes": policy.approval_expiry_minutes,
            },
        }
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
