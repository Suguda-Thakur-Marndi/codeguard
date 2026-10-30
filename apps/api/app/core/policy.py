"""Deterministic Tool & Operation Authorization Policy Engine for CodeGuard."""

import enum
from datetime import UTC, datetime
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, Field


class PrincipalRole(enum.StrEnum):
    MEMBER = "MEMBER"
    REVIEWER = "REVIEWER"
    ADMIN = "ADMIN"
    AGENT = "AGENT"
    SERVICE = "SERVICE"


class Principal(BaseModel):
    """Authenticated caller principal representation."""

    principal_id: str
    role: PrincipalRole
    organization_id: str
    is_ai_agent: bool = False
    metadata: dict[str, str] = {}


class ToolRiskLevel(enum.StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    CONSEQUENTIAL = "CONSEQUENTIAL"
    HIGH_RISK = "HIGH_RISK"


ActionRiskLevel = ToolRiskLevel
ToolRiskClassification = ToolRiskLevel


class PolicyDecision(enum.StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ToolAction(enum.StrEnum):
    COMMENT = "COMMENT"
    REQUEST_CHANGES = "REQUEST_CHANGES"


FORBIDDEN_TOOL_ACTIONS = {
    "merge_pull_request": "Automatic PR merge is strictly forbidden in CodeGuard.",
    "branch_delete": "Automatic branch deletion is strictly forbidden.",
    "repository_delete": "Automatic repository deletion is strictly forbidden.",
    "repo_delete": "Automatic repository deletion is strictly forbidden.",
    "secret_access": "Automatic secret or credential access is strictly forbidden.",
    "arbitrary_shell": "Arbitrary shell execution is strictly forbidden outside sandboxed validation.",
    "source_modify": "Direct source code modification is strictly forbidden.",
    "force_push": "Force push operations are strictly forbidden.",
    "admin_operations": "Arbitrary GitHub administrative operations are strictly forbidden.",
}

FORBIDDEN_OPERATIONS = FORBIDDEN_TOOL_ACTIONS

TOOL_RISK_MAP: dict[str, ToolRiskLevel] = {
    # Read-only operations
    "get_pull_request": ToolRiskLevel.READ_ONLY,
    "get_pull_request_diff": ToolRiskLevel.READ_ONLY,
    "get_pull_request_files": ToolRiskLevel.READ_ONLY,
    "get_repository": ToolRiskLevel.READ_ONLY,
    "get_file": ToolRiskLevel.READ_ONLY,
    "get_symbol": ToolRiskLevel.READ_ONLY,
    "find_references": ToolRiskLevel.READ_ONLY,
    "get_dependencies": ToolRiskLevel.READ_ONLY,
    "get_tests": ToolRiskLevel.READ_ONLY,
    "get_review_findings": ToolRiskLevel.READ_ONLY,
    "get_review_evidence": ToolRiskLevel.READ_ONLY,
    # Controlled operational actions
    "run_validation": ToolRiskLevel.LOW_RISK,
    "submit_review": ToolRiskLevel.CONSEQUENTIAL,
}


def classify_tool_risk(tool_name: str, parameters: dict | None = None) -> ToolRiskLevel:
    """Classifies an action risk level dynamically based on action and parameters."""
    if tool_name == "submit_review" and parameters and parameters.get("action") == "REQUEST_CHANGES":
        return ToolRiskLevel.HIGH_RISK
    return TOOL_RISK_MAP.get(tool_name, ToolRiskLevel.HIGH_RISK)


class GetPullRequestInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    pull_request_number: int = Field(..., ge=1, description="GitHub Pull Request number")


class GetPullRequestDiffInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    pull_request_number: int = Field(..., ge=1, description="GitHub Pull Request number")


class GetPullRequestFilesInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    pull_request_number: int = Field(..., ge=1, description="GitHub Pull Request number")


class GetRepositoryInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")


class GetFileInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    commit_sha: str = Field(..., min_length=7, max_length=40, description="Commit SHA")
    file_path: str = Field(..., description="Relative path to file in repo")


class GetSymbolInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    commit_sha: str = Field(..., min_length=7, max_length=40, description="Commit SHA")
    symbol_name: str = Field(..., description="Fully qualified symbol name")


class FindReferencesInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    commit_sha: str = Field(..., min_length=7, max_length=40, description="Commit SHA")
    symbol_name: str = Field(..., description="Target symbol name")


class GetDependenciesInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    commit_sha: str = Field(..., min_length=7, max_length=40, description="Commit SHA")
    file_path: str = Field(..., description="Target file path")


class GetTestsInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    commit_sha: str = Field(..., min_length=7, max_length=40, description="Commit SHA")
    target_file: str = Field(..., description="Source code file path to query associated tests for")


class GetReviewFindingsInput(BaseModel):
    review_job_id: str = Field(..., description="Review job UUID")


class GetReviewEvidenceInput(BaseModel):
    finding_id: str = Field(..., description="Finding UUID")


class RunValidationInput(BaseModel):
    review_job_id: str = Field(..., description="Review job UUID")
    finding_id: str = Field(..., description="Candidate finding UUID")
    scenario_id: str = Field(..., description="Validation scenario identifier")


class SubmitReviewInput(BaseModel):
    repository_id: str = Field(..., description="Internal repository UUID")
    pull_request_number: int = Field(..., ge=1, description="GitHub Pull Request number")
    head_sha: str = Field(..., min_length=7, max_length=40, description="Target PR HEAD SHA")
    review_job_id: str = Field(..., description="Review job UUID containing verified findings")
    action: Literal["COMMENT", "REQUEST_CHANGES"] = Field(
        default="COMMENT", description="Review action: COMMENT or REQUEST_CHANGES"
    )
    approval_id: str | None = Field(
        default=None, description="Approval request ID if action required human authorization"
    )


TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "get_pull_request": GetPullRequestInput,
    "get_pull_request_diff": GetPullRequestDiffInput,
    "get_pull_request_files": GetPullRequestFilesInput,
    "get_repository": GetRepositoryInput,
    "get_file": GetFileInput,
    "get_symbol": GetSymbolInput,
    "find_references": FindReferencesInput,
    "get_dependencies": GetDependenciesInput,
    "get_tests": GetTestsInput,
    "get_review_findings": GetReviewFindingsInput,
    "get_review_evidence": GetReviewEvidenceInput,
    "run_validation": RunValidationInput,
    "submit_review": SubmitReviewInput,
}


class AuthorizationResult(NamedTuple):
    decision: PolicyDecision
    reason: str
    risk_level: ToolRiskLevel
    requires_approval: bool


class PolicyEngine:
    """
    Deterministic authorization engine enforcing zero-trust boundaries over AI agent operations.
    The LLM is untrusted. Authorization is strictly decided by application code.
    """

    @classmethod
    def evaluate(
        cls,
        principal: Principal,
        organization_id: str,
        repository_id: str | None = None,
        tool_name: str = "",
        parameters: dict[str, Any] | None = None,
        org_policy: dict[str, Any] | None = None,
        approval_record: dict[str, Any] | None = None,
        findings_metadata: list[dict[str, Any]] | None = None,
    ) -> AuthorizationResult:
        # 1. Reject forbidden actions immediately
        if tool_name in FORBIDDEN_TOOL_ACTIONS:
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason=FORBIDDEN_TOOL_ACTIONS[tool_name],
                risk_level=ToolRiskLevel.HIGH_RISK,
                requires_approval=False,
            )

        # 2. Lookup registered risk level
        risk_level = TOOL_RISK_MAP.get(tool_name)
        if risk_level is None:
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason=f"Action '{tool_name}' is not registered in the Security Policy Registry.",
                risk_level=ToolRiskLevel.HIGH_RISK,
                requires_approval=False,
            )

        # 3. Read-only operations are universally safe for authenticated callers
        if risk_level == ToolRiskLevel.READ_ONLY:
            return AuthorizationResult(
                decision=PolicyDecision.ALLOW,
                reason="Read-only operation permitted for authenticated principal.",
                risk_level=ToolRiskLevel.READ_ONLY,
                requires_approval=False,
            )

        # 4. Low-risk operations (sandboxed validation)
        if tool_name == "run_validation":
            return AuthorizationResult(
                decision=PolicyDecision.ALLOW,
                reason="Validation execution in isolated sandbox permitted.",
                risk_level=ToolRiskLevel.LOW_RISK,
                requires_approval=False,
            )

        # 5. Consequential / High-risk operation: submit_review
        if tool_name == "submit_review":
            return cls._evaluate_submit_review(
                principal=principal,
                organization_id=organization_id,
                repository_id=repository_id,
                parameters=parameters or {},
                org_policy=org_policy or {},
                approval_record=approval_record,
                findings_metadata=findings_metadata or [],
            )

        # Default fallback
        return AuthorizationResult(
            decision=PolicyDecision.DENY,
            reason=f"No authorization policy configured for action '{tool_name}'.",
            risk_level=risk_level,
            requires_approval=False,
        )

    @classmethod
    def _evaluate_submit_review(
        cls,
        principal: Principal,
        organization_id: str,
        repository_id: str | None,
        parameters: dict[str, Any],
        org_policy: dict[str, Any],
        approval_record: dict[str, Any] | None,
        findings_metadata: list[dict[str, Any]],
    ) -> AuthorizationResult:
        action = parameters.get("action", "COMMENT")
        head_sha = parameters.get("head_sha", "")

        # A. Check Organization baseline permissions
        allow_ai_comments = org_policy.get("allow_ai_github_comments", True)
        if not allow_ai_comments:
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason="Organization policy has disabled all automated AI GitHub comments.",
                risk_level=ToolRiskLevel.CONSEQUENTIAL,
                requires_approval=False,
            )

        allow_request_changes = org_policy.get("allow_request_changes", False)
        if action == "REQUEST_CHANGES" and not allow_request_changes:
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason="Organization policy forbids AI agents from submitting REQUEST_CHANGES reviews.",
                risk_level=ToolRiskLevel.HIGH_RISK,
                requires_approval=False,
            )

        # B. Verify finding status integrity: Only PUBLISHABLE findings can be published
        for f in findings_metadata:
            status = f.get("status", "")
            if status not in ("PUBLISHABLE", "PUBLISHED"):
                return AuthorizationResult(
                    decision=PolicyDecision.DENY,
                    reason=f"Finding '{f.get('id')}' is in status '{status}'. Only PUBLISHABLE findings can be published.",
                    risk_level=ToolRiskLevel.CONSEQUENTIAL,
                    requires_approval=False,
                )

        # C. Determine whether human approval is required
        requires_approval = False
        severities = {f.get("final_severity") or f.get("severity") for f in findings_metadata}

        if action == "REQUEST_CHANGES":
            requires_approval = True
        elif "CRITICAL" in severities and org_policy.get("require_approval_for_critical", True):
            requires_approval = True
        elif "HIGH" in severities and org_policy.get("require_approval_for_high", True):
            requires_approval = True
        elif "MEDIUM" in severities:
            requires_approval = True
        elif "LOW" in severities and not org_policy.get("auto_publish_low", False):
            requires_approval = True
        elif "ADVISORY" in severities and not org_policy.get("auto_publish_advisory", False):
            requires_approval = True

        effective_risk = ToolRiskLevel.HIGH_RISK if action == "REQUEST_CHANGES" else ToolRiskLevel.CONSEQUENTIAL

        if not requires_approval:
            return AuthorizationResult(
                decision=PolicyDecision.ALLOW,
                reason="Review publication allowed by policy (auto-publish enabled for low/advisory findings).",
                risk_level=effective_risk,
                requires_approval=False,
            )

        # D. Approval IS required: Validate attached approval record
        if not approval_record:
            return AuthorizationResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                reason=f"Action '{action}' with findings {list(severities)} requires human reviewer approval.",
                risk_level=effective_risk,
                requires_approval=True,
            )

        if approval_record.get("status") != "APPROVED":
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason=f"Approval request '{approval_record.get('id')}' is in status '{approval_record.get('status')}', not APPROVED.",
                risk_level=effective_risk,
                requires_approval=True,
            )

        if approval_record.get("head_sha") != head_sha:
            appr_sha = str(approval_record.get("head_sha") or "")[:8]
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason=f"Approval is bound to head SHA {appr_sha}, but current PR head SHA is {head_sha[:8]}. Approval is STALE.",
                risk_level=effective_risk,
                requires_approval=True,
            )

        # Check repository binding if present
        appr_repo = approval_record.get("repository_id")
        if appr_repo and repository_id and appr_repo != repository_id:
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason=f"Approval request '{approval_record.get('id')}' is bound to repository '{appr_repo}', not target repository '{repository_id}'.",
                risk_level=effective_risk,
                requires_approval=True,
            )

        # Check organization binding if present
        appr_org = approval_record.get("organization_id")
        if appr_org and organization_id and appr_org != organization_id:
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason=f"Approval request '{approval_record.get('id')}' belongs to another organization '{appr_org}'.",
                risk_level=effective_risk,
                requires_approval=True,
            )

        expires_at = approval_record.get("expires_at")
        if expires_at:
            if isinstance(expires_at, str):
                expires_at_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            else:
                expires_at_dt = expires_at
            if expires_at_dt.tzinfo is None:
                expires_at_dt = expires_at_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) > expires_at_dt:
                return AuthorizationResult(
                    decision=PolicyDecision.DENY,
                    reason=f"Approval request '{approval_record.get('id')}' has expired.",
                    risk_level=effective_risk,
                    requires_approval=True,
                )

        approver = approval_record.get("approved_by") or ""
        if "agent" in approver.lower() or approver == principal.principal_id and principal.is_ai_agent:
            return AuthorizationResult(
                decision=PolicyDecision.DENY,
                reason="AI agents cannot approve their own actions. An authorized human reviewer is required.",
                risk_level=effective_risk,
                requires_approval=True,
            )

        return AuthorizationResult(
            decision=PolicyDecision.ALLOW,
            reason=f"Action authorized by verified human approval '{approval_record.get('id')}'.",
            risk_level=effective_risk,
            requires_approval=False,
        )
