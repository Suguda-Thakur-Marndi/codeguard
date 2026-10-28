"""Security utilities: HMAC webhook verification and authentication."""

import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)


def verify_github_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Verify GitHub webhook signature using HMAC-SHA256 in constant time.

    Args:
        raw_body: Exact raw bytes of the request body.
        signature_header: The value of the X-Hub-Signature-256 header.

    Returns:
        bool: True if signature is valid, False otherwise.
    """
    if not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[len("sha256=") :]
    secret_bytes = settings.GITHUB_WEBHOOK_SECRET.encode("utf-8")

    mac = hmac.new(secret_bytes, msg=raw_body, digestmod=hashlib.sha256)
    computed_signature = mac.hexdigest()

    return hmac.compare_digest(computed_signature, expected_signature)


async def get_current_user_or_bypass(
    request: Request,
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    x_dev_token: str | None = Header(None, alias="X-Dev-Token"),
) -> dict:
    """
    Authenticate request or grant development session when DEV_AUTH_BYPASS is active.

    Production must use verified JWT tokens or session cookies.
    """
    x_org_id = request.headers.get("X-Organization-Id")

    # 1. Token / Session authentication check
    token = None
    if auth_header and auth_header.credentials:
        token = auth_header.credentials
    elif request.cookies.get("codeguard_session"):
        token = request.cookies.get("codeguard_session")
    elif x_dev_token:
        token = x_dev_token

    # 2. Dev auth bypass if no token provided, explicitly enabled, and in allowed environment
    if not token:
        if settings.DEV_AUTH_BYPASS and settings.APP_ENV in ("development", "test"):
            role_header = request.headers.get("X-User-Role")
            user_id_header = request.headers.get("X-User-Id")
            return {
                "id": user_id_header or "dev-user-001",
                "login": "developer",
                "email": "dev@codeguard.local",
                "role": role_header.lower() if role_header else "admin",
                "organization_id": x_org_id,
                "is_dev": True,
            }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate dev token only when DEV_AUTH_BYPASS is active in allowed environments
    if token == settings.DEV_AUTH_TOKEN:
        if settings.DEV_AUTH_BYPASS and settings.APP_ENV in ("development", "test"):
            role_header = request.headers.get("X-User-Role")
            user_id_header = request.headers.get("X-User-Id")
            return {
                "id": user_id_header or "dev-token-user",
                "login": "dev-token-user",
                "email": "dev-token@codeguard.local",
                "role": role_header.lower() if role_header else "developer",
                "organization_id": x_org_id,
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Development token is disabled or forbidden in this environment",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # If an actual JWT is supplied, decode it safely
    try:
        import jwt
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        jwt_org = payload.get("organization_id") or payload.get("org_id")
        effective_org = jwt_org if jwt_org else (x_org_id if settings.APP_ENV != "production" else None)
        return {
            "id": payload.get("sub"),
            "login": payload.get("name") or payload.get("login", "unknown"),
            "email": payload.get("email"),
            "role": payload.get("role", "user"),
            "picture": payload.get("picture"),
            "organization_id": effective_org,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def verify_tenant_access(current_user: dict, target_org_id: str | None) -> None:
    """
    Ensure the authenticated principal has authorization to access the target organization's resources.

    Enforcement rules:
    1. If user has no organization_id (e.g. system worker or unconstrained dev principal), access is permitted.
    2. If user has an organization_id, target_org_id MUST match. Any mismatch is strictly rejected with 403 Forbidden.
    """
    if not target_org_id:
        return
    user_org_id = current_user.get("organization_id")
    if not user_org_id:
        return
    if str(user_org_id) != str(target_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access forbidden",
        )
