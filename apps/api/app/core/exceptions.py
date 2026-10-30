"""CodeGuard exception hierarchy with retry classification."""

from typing import Any


class CodeGuardException(Exception):
    """Base domain exception for CodeGuard."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.retryable = retryable


class WebhookVerificationError(CodeGuardException):
    """Raised when GitHub webhook signature verification fails."""

    def __init__(self, message: str = "Invalid GitHub webhook signature", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="INVALID_WEBHOOK_SIGNATURE",
            status_code=401,
            details=details,
            retryable=False,
        )


class EntityNotFoundError(CodeGuardException):
    """Raised when a requested domain entity cannot be found."""

    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(
            message=f"{entity_name} with ID '{entity_id}' not found",
            code="NOT_FOUND",
            status_code=404,
            details={"entity": entity_name, "id": str(entity_id)},
            retryable=False,
        )


class DuplicateJobError(CodeGuardException):
    """Raised when an active review job already exists for the commit/PR."""

    def __init__(self, message: str = "Review job already active or processed for this commit", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="DUPLICATE_JOB",
            status_code=409,
            details=details,
            retryable=False,
        )


class GitHubAPIError(CodeGuardException):
    """Base exception for external GitHub API errors."""

    def __init__(
        self,
        message: str,
        code: str = "GITHUB_API_ERROR",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
            retryable=retryable,
        )


class GitHubRateLimitError(GitHubAPIError):
    """Raised when GitHub returns 403 or 429 rate limit exceeded."""

    def __init__(self, retry_after: int = 60, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"GitHub API rate limit exceeded. Retry after {retry_after}s",
            code="GITHUB_RATE_LIMIT",
            status_code=429,
            details=details or {"retry_after_seconds": retry_after},
            retryable=True,
        )
        self.retry_after = retry_after


class GitHubNotFoundError(GitHubAPIError):
    """Raised when repository or PR is not found on GitHub."""

    def __init__(self, resource: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"GitHub resource '{resource}' not found",
            code="GITHUB_NOT_FOUND",
            status_code=404,
            details=details,
            retryable=False,
        )


class GitHubAuthError(GitHubAPIError):
    """Raised when GitHub App authentication or token generation fails."""

    def __init__(self, message: str = "GitHub App authentication failed", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="GITHUB_AUTH_ERROR",
            status_code=401,
            details=details,
            retryable=False,
        )
