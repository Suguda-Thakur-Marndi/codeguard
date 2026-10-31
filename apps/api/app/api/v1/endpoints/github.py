"""GitHub App connection and repository discovery endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.exceptions import EntityNotFoundError, GitHubAPIError
from app.core.security import get_current_user_or_bypass
from app.db.session import get_db
from app.schemas.github import (
    GitHubAccessibleRepositoriesResponse,
    GitHubConnectRepositoryRequest,
    GitHubDisconnectResponse,
    GitHubInstallationItem,
    GitHubInstallationVerifyRequest,
    GitHubInstallationVerifyResponse,
    GitHubInstallUrlResponse,
)
from app.schemas.repository import RepositoryRead
from app.services.github_service import GitHubService

router = APIRouter(prefix="/github", tags=["GitHub App"])


@router.get(
    "/status",
    summary="Check GitHub App configuration readiness",
)
def get_github_app_status(
    _user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    """Inspect GitHub App settings and report readiness (never exposes secrets)."""
    from app.github.auth import validate_github_app_settings

    statuses = validate_github_app_settings()
    is_ready = all(v == "CONFIGURED" for v in statuses.values())
    return {
        "ready": is_ready,
        "settings": statuses,
    }


@router.get(
    "/install-url",
    response_model=GitHubInstallUrlResponse,
    summary="Get GitHub App installation URL",
)
def get_install_url(
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> GitHubInstallUrlResponse:
    """Retrieve the official GitHub App installation URL for CodeGuard."""
    service = GitHubService(db)
    return service.get_install_url()


@router.get(
    "/installations",
    response_model=list[GitHubInstallationItem],
    summary="List registered GitHub App installations",
)
def list_installations(
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> list[GitHubInstallationItem]:
    """List all GitHub App installations and connected organization accounts."""
    service = GitHubService(db)
    return service.list_installations()


@router.post(
    "/installations/verify",
    response_model=GitHubInstallationVerifyResponse,
    summary="Verify and link a GitHub App installation",
)
async def verify_installation(
    body: GitHubInstallationVerifyRequest,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> GitHubInstallationVerifyResponse:
    """Validate installation with GitHub API and ensure Organization record is registered."""
    service = GitHubService(db)
    try:
        res = await service.verify_installation(body.installation_id)
        # Ensure the verifying user is registered as active OWNER of the organization
        user_id = _user.get("id")
        if user_id and not _user.get("is_dev"):
            from app.models.membership import (
                MembershipRole,
                MembershipStatus,
                UserOrganizationMembership,
            )

            existing_m = (
                db.query(UserOrganizationMembership)
                .filter(
                    UserOrganizationMembership.user_id == user_id,
                    UserOrganizationMembership.organization_id == res.id,
                )
                .first()
            )
            if not existing_m:
                new_m = UserOrganizationMembership(
                    user_id=user_id,
                    organization_id=res.id,
                    role=MembershipRole.OWNER.value,
                    status=MembershipStatus.ACTIVE.value,
                )
                db.add(new_m)
                db.commit()
        return res
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc


@router.get(
    "/installations/{installation_id}/repositories",
    response_model=GitHubAccessibleRepositoriesResponse,
    summary="List repositories accessible via GitHub installation",
)
async def list_installation_repositories(
    installation_id: int,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> GitHubAccessibleRepositoriesResponse:
    """Retrieve repositories granted to this installation and annotate connection status."""
    service = GitHubService(db)
    try:
        return await service.list_accessible_repositories(installation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        ) from exc


@router.post(
    "/repositories/connect",
    response_model=RepositoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Connect a GitHub repository to CodeGuard",
)
async def connect_repository(
    body: GitHubConnectRepositoryRequest,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> RepositoryRead:
    """Register repository under the verified installation organization and enable review capabilities."""
    service = GitHubService(db)
    try:
        repo = await service.connect_repository(body)
        return RepositoryRead.model_validate(repo)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc


@router.delete(
    "/repositories/{repository_id}",
    response_model=GitHubDisconnectResponse,
    summary="Disconnect a repository from CodeGuard",
)
def disconnect_repository(
    repository_id: str,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> GitHubDisconnectResponse:
    """Remove repository from CodeGuard while leaving the GitHub App installation intact."""
    service = GitHubService(db)
    try:
        service.disconnect_repository(repository_id)
        return GitHubDisconnectResponse(
            success=True,
            message="Repository disconnected successfully",
            repository_id=repository_id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
