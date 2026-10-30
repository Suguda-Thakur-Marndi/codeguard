"""GitHub App JWT generation and Installation token provider."""

import time
from datetime import datetime
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.core.config import settings
from app.core.exceptions import GitHubAuthError
from app.core.logging import TimingLogger, logger


def find_repo_root() -> Path:
    """Find the root directory of the CodeGuard repository."""
    start_dir = Path(__file__).resolve()
    for parent in [start_dir] + list(start_dir.parents):
        if (parent / ".git").is_dir() or (parent / "package.json").is_file():
            return parent
        if (parent / "apps" / "api").is_dir() and (parent / "apps" / "web").is_dir():
            return parent
    return start_dir.parents[3]


def is_valid_rsa_pem_key(key_data: str) -> bool:
    """Validate whether key_data contains a valid PEM-encoded RSA private key."""
    if not key_data or not isinstance(key_data, str):
        return False
    try:
        clean_key = key_data.strip().replace("\\n", "\n")
        loaded_key = serialization.load_pem_private_key(
            clean_key.encode("utf-8"),
            password=None,
        )
        return isinstance(loaded_key, RSAPrivateKey)
    except Exception:
        return False


def resolve_private_key_path(configured_path: str | None) -> Path | None:
    """
    Resolve a configured private key path across:
    - Absolute path
    - Current working directory
    - Repository root
    - apps/api directory relative to repo root or cwd
    """
    if not configured_path or not configured_path.strip():
        return None

    raw_path = Path(configured_path.strip())
    if raw_path.is_absolute():
        if raw_path.is_file():
            return raw_path.resolve()
        return None

    repo_root = find_repo_root()
    cwd = Path.cwd()

    candidate_locations = [
        cwd / raw_path,
        repo_root / raw_path,
        repo_root / "apps" / "api" / raw_path,
        cwd / "apps" / "api" / raw_path,
    ]

    seen = set()
    for candidate in candidate_locations:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved

    return None


def auto_discover_repo_private_key() -> Path | None:
    """Search for existing *.private-key.pem file in repository root or apps/api."""
    repo_root = find_repo_root()
    search_dirs = [repo_root, repo_root / "apps" / "api", Path.cwd()]
    seen = set()
    for directory in search_dirs:
        dir_resolved = directory.resolve()
        if dir_resolved in seen or not dir_resolved.is_dir():
            continue
        seen.add(dir_resolved)
        # Search for *.private-key.pem first
        for pem_file in sorted(dir_resolved.glob("*.private-key.pem")):
            if pem_file.is_file():
                try:
                    with open(pem_file, encoding="utf-8") as f:
                        content = f.read()
                    if is_valid_rsa_pem_key(content):
                        return pem_file.resolve()
                except Exception:
                    continue
        # Fallback to any *.pem that is a valid RSA private key
        for pem_file in sorted(dir_resolved.glob("*.pem")):
            if pem_file.is_file():
                try:
                    with open(pem_file, encoding="utf-8") as f:
                        content = f.read()
                    if is_valid_rsa_pem_key(content):
                        return pem_file.resolve()
                except Exception:
                    continue
    return None


def validate_github_app_settings(
    installation_id: int | None = None,
) -> dict[str, str]:
    """
    Validate presence and usability of GitHub App configuration settings.
    Returns status mapping for each setting: 'CONFIGURED', 'MISSING', 'PLACEHOLDER', or 'INVALID'.
    Never logs or exposes secret values.
    """
    statuses: dict[str, str] = {}

    # 1. GITHUB_APP_ID
    app_id = str(settings.GITHUB_APP_ID or "").strip()
    if not app_id:
        statuses["GITHUB_APP_ID"] = "MISSING"
    elif app_id in ("dev-app-id", "placeholder"):
        statuses["GITHUB_APP_ID"] = "PLACEHOLDER"
    elif app_id.isdigit():
        statuses["GITHUB_APP_ID"] = "CONFIGURED"
    else:
        statuses["GITHUB_APP_ID"] = "INVALID"

    # 2. GITHUB_APP_SLUG
    slug = str(settings.GITHUB_APP_SLUG or "").strip()
    if not slug:
        statuses["GITHUB_APP_SLUG"] = "MISSING"
    elif slug in ("dev-app-slug", "placeholder"):
        statuses["GITHUB_APP_SLUG"] = "PLACEHOLDER"
    else:
        statuses["GITHUB_APP_SLUG"] = "CONFIGURED"

    # 3. GITHUB_PRIVATE_KEY
    if settings.GITHUB_PRIVATE_KEY and settings.GITHUB_PRIVATE_KEY.strip():
        if is_valid_rsa_pem_key(settings.GITHUB_PRIVATE_KEY):
            statuses["GITHUB_PRIVATE_KEY"] = "CONFIGURED"
        else:
            statuses["GITHUB_PRIVATE_KEY"] = "INVALID"
    elif settings.GITHUB_PRIVATE_KEY_PATH and settings.GITHUB_PRIVATE_KEY_PATH.strip():
        resolved = resolve_private_key_path(settings.GITHUB_PRIVATE_KEY_PATH)
        if not resolved:
            statuses["GITHUB_PRIVATE_KEY"] = "INVALID"
        else:
            try:
                with open(resolved, encoding="utf-8") as f:
                    content = f.read()
                if is_valid_rsa_pem_key(content):
                    statuses["GITHUB_PRIVATE_KEY"] = "CONFIGURED"
                else:
                    statuses["GITHUB_PRIVATE_KEY"] = "INVALID"
            except Exception:
                statuses["GITHUB_PRIVATE_KEY"] = "INVALID"
    else:
        # Check auto-discovery
        auto_p = auto_discover_repo_private_key()
        if auto_p:
            statuses["GITHUB_PRIVATE_KEY"] = "CONFIGURED"
        else:
            statuses["GITHUB_PRIVATE_KEY"] = "MISSING"

    # 4. GITHUB_WEBHOOK_SECRET
    wh_secret = str(settings.GITHUB_WEBHOOK_SECRET or "").strip()
    if not wh_secret:
        statuses["GITHUB_WEBHOOK_SECRET"] = "MISSING"
    elif wh_secret in ("dev-webhook-secret", "placeholder", "secret"):
        statuses["GITHUB_WEBHOOK_SECRET"] = "PLACEHOLDER"
    else:
        statuses["GITHUB_WEBHOOK_SECRET"] = "CONFIGURED"

    # 5. Target installation ID (if provided)
    if installation_id is not None:
        if installation_id <= 0:
            statuses["target_installation_id"] = "INVALID"
        elif installation_id == 1 and settings.APP_ENV in ("development", "test"):
            statuses["target_installation_id"] = "PLACEHOLDER"
        else:
            statuses["target_installation_id"] = "CONFIGURED"

    return statuses


def assert_ready_for_github_operations(installation_id: int | None = None) -> None:
    """
    Assert that all required GitHub App settings are ready for live operations.
    Raises GitHubAuthError with safe details if any setting is not CONFIGURED.
    """
    statuses = validate_github_app_settings(installation_id=installation_id)
    blockers = [f"{k}: {v}" for k, v in statuses.items() if v != "CONFIGURED"]
    if blockers:
        raise GitHubAuthError(
            f"GitHub App settings are not ready for live operations. Issues detected: {', '.join(blockers)}. "
            "Please configure real values in .env. Refer to docs/operations/GITHUB_APP_SETUP.md for instructions."
        )


class GitHubAppAuth:
    """Handles GitHub App authentication using RS256 JWTs and installation access tokens."""

    def __init__(
        self,
        app_id: str | int | None = None,
        private_key: str | None = None,
        private_key_path: str | None = None,
    ):
        raw_app_id = app_id if app_id is not None else settings.GITHUB_APP_ID
        self.app_id: str = str(raw_app_id).strip()
        self.private_key_path: str | None = None

        # 1. If explicit argument is passed to __init__, respect the caller's explicit parameter
        if private_key is not None:
            if private_key.strip():
                clean_inline = private_key.strip().replace("\\n", "\n")
                if not is_valid_rsa_pem_key(clean_inline):
                    raise GitHubAuthError(
                        "Configured GITHUB_PRIVATE_KEY is not a valid PEM RSA private key."
                    )
                self.private_key = clean_inline
                self.private_key_path = "inline"
            else:
                self.private_key = None
        elif private_key_path is not None:
            if private_key_path.strip():
                resolved = resolve_private_key_path(private_key_path)
                if not resolved:
                    raise GitHubAuthError(
                        f"Configured GITHUB_PRIVATE_KEY_PATH '{private_key_path}' does not exist or cannot be resolved."
                    )
                try:
                    with open(resolved, encoding="utf-8") as f:
                        content = f.read().strip()
                except Exception as read_err:
                    raise GitHubAuthError(
                        f"Failed to read private key from '{resolved}': {read_err}"
                    ) from read_err

                if not is_valid_rsa_pem_key(content):
                    raise GitHubAuthError(
                        f"Private key file at '{resolved}' is not a valid PEM RSA private key."
                    )
                self.private_key = content
                self.private_key_path = str(resolved)
            else:
                self.private_key = None
        else:
            # 2. Neither argument passed; inspect global settings
            configured_path = settings.GITHUB_PRIVATE_KEY_PATH
            if configured_path and configured_path.strip():
                resolved = resolve_private_key_path(configured_path)
                if not resolved:
                    raise GitHubAuthError(
                        f"Configured GITHUB_PRIVATE_KEY_PATH '{configured_path}' does not exist or cannot be resolved."
                    )
                try:
                    with open(resolved, encoding="utf-8") as f:
                        content = f.read().strip()
                except Exception as read_err:
                    raise GitHubAuthError(
                        f"Failed to read private key from '{resolved}': {read_err}"
                    ) from read_err

                if not is_valid_rsa_pem_key(content):
                    raise GitHubAuthError(
                        f"Private key file at '{resolved}' is not a valid PEM RSA private key."
                    )
                self.private_key = content
                self.private_key_path = str(resolved)
            elif settings.GITHUB_PRIVATE_KEY and settings.GITHUB_PRIVATE_KEY.strip():
                clean_inline = settings.GITHUB_PRIVATE_KEY.strip().replace("\\n", "\n")
                if not is_valid_rsa_pem_key(clean_inline):
                    raise GitHubAuthError(
                        "Configured GITHUB_PRIVATE_KEY is not a valid PEM RSA private key."
                    )
                self.private_key = clean_inline
                self.private_key_path = "inline"
            elif self.app_id not in ("dev-app-id", ""):
                auto_path = auto_discover_repo_private_key()
                if auto_path:
                    try:
                        with open(auto_path, encoding="utf-8") as f:
                            content = f.read().strip()
                        if is_valid_rsa_pem_key(content):
                            self.private_key = content
                            self.private_key_path = str(auto_path)
                        else:
                            self.private_key = None
                    except Exception:
                        self.private_key = None
                else:
                    self.private_key = None
            else:
                self.private_key = None

        # In-memory cache for installation tokens: {installation_id: (token, expiry_timestamp)}
        self._token_cache: dict[int, tuple[str, float]] = {}

    def generate_app_jwt(self) -> str:
        """Generate RS256 JWT valid for 10 minutes to authenticate as the GitHub App."""
        # When running without private key in dev/testing with dev-app-id, return mock
        if not self.private_key and self.app_id in ("dev-app-id", "") and settings.APP_ENV in ("development", "test"):
            return "mock-github-app-jwt"

        if not self.private_key:
            raise GitHubAuthError(
                "Missing GitHub App private key. Ensure GITHUB_PRIVATE_KEY_PATH or GITHUB_PRIVATE_KEY is configured."
            )

        # Reject development placeholder when real signing is attempted
        if self.app_id in ("dev-app-id", "", None):
            raise GitHubAuthError(
                "GITHUB_APP_ID cannot be 'dev-app-id' or empty for GitHub App JWT signing. "
                "Please configure your numeric GitHub App ID."
            )

        iss_val: str = str(self.app_id).strip()
        if not iss_val.isdigit():
            raise GitHubAuthError(
                f"Invalid GITHUB_APP_ID format: App ID must contain numeric digits, got '{iss_val}'."
            )

        now = int(time.time())
        # RFC 7519 & GitHub App JWT requirements:
        # - algorithm: RS256
        # - iat: 60 seconds in the past for clock drift
        # - exp: maximum 10 minutes from iat (600s total duration, 540s from current wall clock)
        payload = {
            "iat": now - 60,
            "exp": now + 540,
            "iss": iss_val,
        }

        try:
            private_key = self.private_key.replace("\\n", "\n")
            return jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as e:
            logger.error("Failed to sign GitHub App JWT", exc_info=True)
            raise GitHubAuthError(f"Failed to generate GitHub App JWT: {str(e)}") from e

    async def get_installation_access_token(
        self,
        installation_id: int,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        """Fetch or return cached installation access token from GitHub."""
        now = time.time()
        if installation_id in self._token_cache:
            cached_token, expires_at = self._token_cache[installation_id]
            # Reuse token if it has at least 60 seconds before expiring
            if expires_at - now > 60:
                return cached_token

        # In dev/test environment without valid credentials or with dev-app-id, return mock token
        if (not self.private_key or self.app_id in ("dev-app-id", "")) and settings.APP_ENV in ("development", "test"):
            mock_token = f"ghs_mock_token_for_{installation_id}"
            self._token_cache[installation_id] = (mock_token, now + 3600)
            return mock_token

        app_jwt = self.generate_app_jwt()
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CodeGuard-AI/0.1.0",
        }

        with TimingLogger("github_api_installation_token", {"installation_id": installation_id}):
            if client is not None:
                resp = await client.post(url, headers=headers, timeout=15.0)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await c.post(url, headers=headers, timeout=15.0)

            if resp.status_code != 201:
                if resp.status_code == 404:
                    slug = settings.GITHUB_APP_SLUG or "codeguard-ai-123"
                    raise GitHubAuthError(
                        f"GitHub App '{slug}' is not installed for installation ID {installation_id} on GitHub (404 Not Found). "
                        f"Please install the app at https://github.com/apps/{slug}/installations/new to connect your repositories.",
                        details={"status_code": 404, "installation_id": installation_id},
                    )
                raise GitHubAuthError(
                    f"Failed to obtain installation token for {installation_id}: {resp.text}",
                    details={"status_code": resp.status_code},
                )

            data = resp.json()
            token = data["token"]
            # Expiration time parsing
            expires_at_str = data.get("expires_at")
            expires_at_ts = now + 3600
            if expires_at_str:
                try:
                    dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    expires_at_ts = dt.timestamp()
                except Exception:
                    pass

            self._token_cache[installation_id] = (token, expires_at_ts)
            return token
