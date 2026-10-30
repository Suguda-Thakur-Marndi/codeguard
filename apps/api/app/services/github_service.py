"""GitHub connection, installation verification, and repository discovery service."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EntityNotFoundError, GitHubAPIError, GitHubAuthError
from app.core.logging import logger
from app.db.repositories.organization_repo import OrganizationRepository
from app.db.repositories.repository_repo import RepositoryRepository
from app.github.client import GitHubClient
from app.models.organization import Organization
from app.models.repository import Repository
from app.schemas.github import (
    GitHubAccessibleRepositoriesResponse,
    GitHubAccessibleRepository,
    GitHubConnectRepositoryRequest,
    GitHubInstallationItem,
    GitHubInstallationVerifyResponse,
    GitHubInstallUrlResponse,
)


class GitHubService:
    """Service orchestrating GitHub App installations and repository connections."""

    def __init__(self, db: Session, client: GitHubClient | None = None):
        self.db = db
        self.client = client or GitHubClient()
        self.org_repo = OrganizationRepository(db)
        self.repo_repo = RepositoryRepository(db)

    def get_install_url(self) -> GitHubInstallUrlResponse:
        """Resolve the official GitHub App installation URL."""
        slug = settings.GITHUB_APP_SLUG or "codeguard-ai-123"
        url = settings.github_app_install_url
        return GitHubInstallUrlResponse(
            install_url=url,
            app_slug=slug,
            app_id=settings.GITHUB_APP_ID,
        )

    async def verify_installation(self, installation_id: int) -> GitHubInstallationVerifyResponse:
        """Verify GitHub installation metadata with GitHub and register Organization."""
        logger.info(
            f"Verifying GitHub installation {installation_id}",
            extra={"event": "github_installation_verify_start", "extra_fields": {"installation_id": installation_id}},
        )

        try:
            install_data = await self.client.get_installation(installation_id)
        except Exception as exc:
            logger.error(f"Failed to query GitHub API for installation {installation_id}: {exc}")
            raise GitHubAPIError(
                f"Failed to verify GitHub installation {installation_id}: {str(exc)}",
                status_code=400,
            ) from exc

        account = install_data.get("account", {})
        account_id = account.get("id") or 1
        account_login = account.get("login") or f"org-{installation_id}"
        account_type = account.get("type") or "Organization"

        org = self.org_repo.get_or_create(
            installation_id=installation_id,
            account_id=account_id,
            account_login=account_login,
            account_type=account_type,
        )

        logger.info(
            f"GitHub installation {installation_id} verified for organization {account_login} (org_id={org.id})",
            extra={"event": "github_installation_verified", "extra_fields": {"org_id": org.id, "login": account_login}},
        )

        return GitHubInstallationVerifyResponse(
            id=org.id,
            installation_id=org.github_installation_id,
            account_id=org.github_account_id,
            account_login=org.github_account_login,
            account_type=org.account_type,
            verified=True,
            created_at=org.created_at,
        )

    def list_installations(self) -> list[GitHubInstallationItem]:
        """List registered GitHub installations and repository counts."""
        orgs = self.org_repo.get_all(order_by=Organization.created_at.desc())[0]
        results: list[GitHubInstallationItem] = []

        for org in orgs:
            # Count connected repositories for this org
            stmt = select(Repository).where(Repository.organization_id == org.id)
            repos = list(self.db.scalars(stmt).all())
            results.append(
                GitHubInstallationItem(
                    id=org.id,
                    installation_id=org.github_installation_id,
                    account_id=org.github_account_id,
                    account_login=org.github_account_login,
                    account_type=org.account_type,
                    repository_count=len(repos),
                    created_at=org.created_at,
                )
            )

        return results

    async def list_accessible_repositories(
        self, installation_id: int
    ) -> GitHubAccessibleRepositoriesResponse:
        """Fetch all repositories accessible via the GitHub installation token and annotate connection status."""
        org = self.org_repo.get_by_installation_id(installation_id)
        if not org:
            # If not yet registered locally, verify with GitHub first
            verify_res = await self.verify_installation(installation_id)
            org = self.org_repo.get_by_id(verify_res.id)
            if not org:
                raise EntityNotFoundError("Organization", str(installation_id))

        try:
            gh_res = await self.client.list_installation_repositories(installation_id)
        except GitHubAuthError as auth_err:
            logger.warning(f"GitHub installation {installation_id} auth failure: {auth_err}")
            err_code = (auth_err.details or {}).get("status_code", 404) if hasattr(auth_err, "details") else 404
            raise GitHubAPIError(
                auth_err.message,
                status_code=err_code,
            ) from auth_err
        except Exception as exc:
            logger.error(f"Error fetching repositories for installation {installation_id}: {exc}")
            raise GitHubAPIError(
                f"Failed to fetch repositories from GitHub for installation {installation_id}: {str(exc)}",
                status_code=502,
            ) from exc

        gh_repos = gh_res.get("repositories", [])
        total_count = gh_res.get("total_count", len(gh_repos))

        # Query all currently connected repositories in CodeGuard
        all_connected = self.repo_repo.get_all(page=1, page_size=1000)[0]
        connected_map: dict[int, Repository] = {r.github_repo_id: r for r in all_connected}

        annotated_repos: list[GitHubAccessibleRepository] = []
        for r in gh_repos:
            gh_id = r.get("id")
            existing = connected_map.get(gh_id)
            owner_info = r.get("owner")
            owner_login: str = org.github_account_login
            if isinstance(owner_info, dict):
                raw_login = owner_info.get("login")
                if isinstance(raw_login, str) and raw_login:
                    owner_login = raw_login

            annotated_repos.append(
                GitHubAccessibleRepository(
                    github_repo_id=gh_id,
                    name=r.get("name", ""),
                    full_name=r.get("full_name", f"{owner_login}/{r.get('name', '')}"),
                    owner=owner_login,
                    default_branch=r.get("default_branch", "main"),
                    is_private=bool(r.get("private", True)),
                    html_url=r.get("html_url", f"https://github.com/{r.get('full_name', '')}"),
                    description=r.get("description"),
                    is_connected=existing is not None,
                    codeguard_repo_id=existing.id if existing else None,
                )
            )

        return GitHubAccessibleRepositoriesResponse(
            installation_id=installation_id,
            account_login=org.github_account_login,
            total_count=total_count,
            repositories=annotated_repos,
        )

    async def connect_repository(
        self, req: GitHubConnectRepositoryRequest
    ) -> Repository:
        """Connect a specific GitHub repository into CodeGuard under the verified organization."""
        org = self.org_repo.get_by_installation_id(req.installation_id)
        if not org:
            # Verify and link installation if not present
            verify_res = await self.verify_installation(req.installation_id)
            org = self.org_repo.get_by_id(verify_res.id)
            if not org:
                raise EntityNotFoundError("Organization", str(req.installation_id))

        repo = self.repo_repo.get_or_create(
            organization_id=org.id,
            github_repo_id=req.github_repo_id,
            owner=req.owner,
            name=req.name,
            full_name=req.full_name,
            default_branch=req.default_branch,
            is_private=req.is_private,
        )

        logger.info(
            f"Connected repository {repo.full_name} (id={repo.id}, gh_id={repo.github_repo_id}) to org {org.github_account_login}",
            extra={"event": "repository_connected", "extra_fields": {"repo_id": repo.id, "gh_repo_id": repo.github_repo_id}},
        )

        return repo

    def disconnect_repository(self, repository_id: str) -> None:
        """Disconnect a repository from CodeGuard while leaving the GitHub App installed on GitHub."""
        repo = self.repo_repo.get_by_id(repository_id)
        if not repo:
            raise EntityNotFoundError("Repository", repository_id)

        full_name = repo.full_name
        self.repo_repo.delete(repo)

        logger.info(
            f"Disconnected repository {full_name} (id={repository_id})",
            extra={"event": "repository_disconnected", "extra_fields": {"repo_id": repository_id, "full_name": full_name}},
        )
