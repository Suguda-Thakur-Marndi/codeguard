"""GitHub connection, installation, and repository schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GitHubInstallUrlResponse(BaseModel):
    """Payload returning the GitHub App installation URL."""

    install_url: str
    app_slug: str
    app_id: str


class GitHubInstallationVerifyRequest(BaseModel):
    """Request payload to verify and link a GitHub App installation."""

    installation_id: int


class GitHubInstallationVerifyResponse(BaseModel):
    """Response payload after verifying an installation."""

    id: str
    installation_id: int
    account_id: int
    account_login: str
    account_type: str
    verified: bool
    created_at: datetime


class GitHubInstallationItem(BaseModel):
    """Summary of a registered GitHub App installation."""

    id: str
    installation_id: int
    account_id: int
    account_login: str
    account_type: str
    repository_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GitHubAccessibleRepository(BaseModel):
    """Metadata for a repository available under a GitHub App installation."""

    github_repo_id: int
    name: str
    full_name: str
    owner: str
    default_branch: str = "main"
    is_private: bool = True
    html_url: str
    description: str | None = None
    is_connected: bool = False
    codeguard_repo_id: str | None = None


class GitHubAccessibleRepositoriesResponse(BaseModel):
    """List of accessible repositories returned for an installation."""

    installation_id: int
    account_login: str
    total_count: int
    repositories: list[GitHubAccessibleRepository]


class GitHubConnectRepositoryRequest(BaseModel):
    """Payload to connect a specific GitHub repository into CodeGuard."""

    installation_id: int
    github_repo_id: int
    owner: str
    name: str
    full_name: str
    default_branch: str = "main"
    is_private: bool = True


class GitHubDisconnectResponse(BaseModel):
    """Response payload after disconnecting a repository."""

    success: bool
    message: str
    repository_id: str
