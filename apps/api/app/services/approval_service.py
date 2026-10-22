"""Approval service managing human authorization workflows and expiration."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.approval_request import ApprovalRequest, ApprovalStatus
from app.models.pull_request import PullRequest


class ApprovalService:
    """Service managing human approval lifecycle for consequential actions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_approval_request(
        self,
        organization_id: str,
        repository_id: str,
        pull_request_id: str,
        review_job_id: str,
        head_sha: str,
        finding_id: str | None = None,
        requested_action: str = "COMMENT",
        risk_level: str = "CONSEQUENTIAL",
        requested_by: str = "agent",
        expiry_minutes: int | None = None,
    ) -> ApprovalRequest:
        """Create a new pending human approval request bound to exact commit head SHA."""
        minutes = expiry_minutes or settings.APPROVAL_EXPIRY_MINUTES_DEFAULT
        expires_at = datetime.now(UTC) + timedelta(minutes=minutes)

        req = ApprovalRequest(
            organization_id=organization_id,
            repository_id=repository_id,
            pull_request_id=pull_request_id,
            review_job_id=review_job_id,
            finding_id=finding_id,
            requested_action=requested_action,
            risk_level=risk_level,
            status=ApprovalStatus.PENDING,
            requested_by=requested_by,
            head_sha=head_sha,
            expires_at=expires_at,
        )
        self.db.add(req)
        self.db.commit()
        self.db.refresh(req)
        return req

    def get_approval_request(self, approval_id: str) -> ApprovalRequest | None:
        return self.db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))

    def list_approval_requests(
        self,
        organization_id: str | None = None,
        repository_id: str | None = None,
        pull_request_id: str | None = None,
        status: ApprovalStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        query = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
        if organization_id:
            query = query.where(ApprovalRequest.organization_id == organization_id)
        if repository_id:
            query = query.where(ApprovalRequest.repository_id == repository_id)
        if pull_request_id:
            query = query.where(ApprovalRequest.pull_request_id == pull_request_id)
        if status:
            query = query.where(ApprovalRequest.status == status)

        return list(self.db.scalars(query.offset(offset).limit(limit)).all())

    def count_approval_requests(
        self,
        organization_id: str | None = None,
        repository_id: str | None = None,
        pull_request_id: str | None = None,
        status: ApprovalStatus | None = None,
    ) -> int:
        from sqlalchemy import func
        query = select(func.count(ApprovalRequest.id))
        if organization_id:
            query = query.where(ApprovalRequest.organization_id == organization_id)
        if repository_id:
            query = query.where(ApprovalRequest.repository_id == repository_id)
        if pull_request_id:
            query = query.where(ApprovalRequest.pull_request_id == pull_request_id)
        if status:
            query = query.where(ApprovalRequest.status == status)

        return self.db.scalar(query) or 0

    def approve_request(
        self,
        approval_id: str,
        approver_principal_id: str,
        approver_role: str,
        is_ai_agent: bool,
        comment: str | None = None,
        approver_organization_id: str | None = None,
    ) -> ApprovalRequest:
        """Approve an approval request with role validation, tenant isolation, and stale commit detection."""
        req = self.get_approval_request(approval_id)
        if not req:
            raise ValueError(f"Approval request '{approval_id}' not found.")

        # Guard 0: Cross-tenant isolation check
        if approver_organization_id and approver_role.upper() != "ADMIN" and approver_organization_id != req.organization_id:
            raise ValueError(f"Cross-tenant authorization denied: principal belongs to organization '{approver_organization_id}', not '{req.organization_id}'.")

        # Guard 1: No AI agent self-approval
        if is_ai_agent or "agent" in approver_principal_id.lower():
            raise ValueError("AI agents cannot approve their own actions. An authorized human reviewer is required.")

        # Guard 2: Role validation
        if approver_role.upper() not in ("REVIEWER", "ADMIN"):
            raise ValueError(f"Principal with role '{approver_role}' is not authorized to approve. REVIEWER or ADMIN required.")

        # Guard 3: Active status check
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot approve request in status '{req.status}'. Only PENDING requests can be approved.")

        # Guard 4: Expiration check
        now = datetime.now(UTC)
        expires_at = req.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if now > expires_at:
            req.status = ApprovalStatus.EXPIRED
            req.resolved_at = now
            self.db.commit()
            raise ValueError(f"Approval request '{approval_id}' has expired.")

        # Guard 5: Stale commit validation (PR HEAD SHA check)
        pr = self.db.scalar(select(PullRequest).where(PullRequest.id == req.pull_request_id))
        if pr and pr.head_sha != req.head_sha:
            req.status = ApprovalStatus.CANCELLED
            req.resolved_at = now
            req.reason = f"Stale approval: PR head updated from {req.head_sha[:8]} to {pr.head_sha[:8]}."
            self.db.commit()
            raise ValueError(f"PR head SHA changed to {pr.head_sha[:8]}. Approval bound to {req.head_sha[:8]} is STALE.")

        req.status = ApprovalStatus.APPROVED
        req.approved_by = approver_principal_id
        req.resolved_at = now
        req.reason = comment or "Approved by human reviewer."
        self.db.commit()
        self.db.refresh(req)
        return req

    def reject_request(
        self,
        approval_id: str,
        approver_principal_id: str,
        approver_role: str,
        is_ai_agent: bool,
        reason: str,
        approver_organization_id: str | None = None,
    ) -> ApprovalRequest:
        """Reject an approval request with reason recorded in audit trail."""
        req = self.get_approval_request(approval_id)
        if not req:
            raise ValueError(f"Approval request '{approval_id}' not found.")

        # Guard 0: Cross-tenant isolation check
        if approver_organization_id and approver_role.upper() != "ADMIN" and approver_organization_id != req.organization_id:
            raise ValueError(f"Cross-tenant authorization denied: principal belongs to organization '{approver_organization_id}', not '{req.organization_id}'.")

        if is_ai_agent or "agent" in approver_principal_id.lower():
            raise ValueError("AI agents cannot reject approvals.")

        if approver_role.upper() not in ("REVIEWER", "ADMIN"):
            raise ValueError(f"Principal with role '{approver_role}' is not authorized. REVIEWER or ADMIN required.")

        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot reject request in status '{req.status}'.")

        now = datetime.now(UTC)
        req.status = ApprovalStatus.REJECTED
        req.approved_by = approver_principal_id
        req.resolved_at = now
        req.reason = reason
        self.db.commit()
        self.db.refresh(req)
        return req
