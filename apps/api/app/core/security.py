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
            options={"require": ["exp", "sub"], "verify_aud": False},
        )
        # Validate issuer and audience if present in token
        if payload.get("iss") and payload["iss"] != "codeguard-ai":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if payload.get("aud") and payload["aud"] != "codeguard-api":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience",
                headers={"WWW-Authenticate": "Bearer"},
            )
        jwt_org = payload.get("organization_id") or payload.get("org_id")
        effective_org = jwt_org if jwt_org else (x_org_id if settings.APP_ENV != "production" else None)
        claimed_orgs = payload.get("organizations")
        if claimed_orgs is None:
            claimed_orgs = [effective_org] if effective_org else []
        return {
            "id": payload.get("sub"),
            "login": payload.get("name") or payload.get("login", "unknown"),
            "email": payload.get("email"),
            "role": payload.get("role", "user"),
            "picture": payload.get("picture"),
            "organization_id": effective_org,
            "organizations": claimed_orgs,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def verify_tenant_access(
    current_user: dict,
    target_org_id: str | None,
    db: object | None = None,
) -> None:
    """
    Ensure the authenticated principal has authorization to access the target organization's resources.

    Enforcement rules:
    1. System workers (role='system') are permitted for background processing.
    2. Users without verified organization membership fail closed (403 Forbidden).
    3. Cross-tenant access is strictly rejected (403 Forbidden).
    4. Real-time active status: When db session is available, membership is validated against
       the database to ensure suspended or revoked memberships immediately fail closed.
    """
    # 1. System worker principal
    if current_user.get("role") == "system":
        return

    # 2. Check for dev-mode bypass without org constraints
    is_dev = bool(
        current_user.get("is_dev")
        and settings.DEV_AUTH_BYPASS
        and settings.APP_ENV in ("development", "test")
    )

    user_org_id = current_user.get("organization_id")
    raw_orgs = current_user.get("organizations")
    allowed_orgs = list(raw_orgs) if raw_orgs else ([] if not user_org_id else [user_org_id])
    if user_org_id and user_org_id not in allowed_orgs:
        allowed_orgs.append(user_org_id)

    # Real-time DB lookup: If user has no organization in token, resolve active memberships from DB
    if db is not None and not is_dev and not allowed_orgs and current_user.get("id"):
        from app.models.membership import MembershipStatus, UserOrganizationMembership

        db_memberships = (
            db.query(UserOrganizationMembership)  # type: ignore[union-attr]
            .filter(
                UserOrganizationMembership.user_id == current_user["id"],
                UserOrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
            .all()
        )
        if db_memberships:
            allowed_orgs = [m.organization_id for m in db_memberships]
            user_org_id = allowed_orgs[0]
            current_user["organization_id"] = user_org_id
            current_user["organizations"] = allowed_orgs

    # If neither target_org_id nor user_org_id is present, ungrounded users cannot access org-scoped resources
    effective_org = target_org_id or user_org_id
    if not effective_org:
        if is_dev:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No verified organization membership for target resource",
        )

    # 3. Cross-tenant isolation check against token claims
    if target_org_id and allowed_orgs:
        if str(target_org_id) not in [str(o) for o in allowed_orgs]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant access forbidden",
            )

    # Fail closed if non-dev user has no allowed orgs
    if not allowed_orgs and not is_dev:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No verified organization membership for target resource",
        )

    # 4. Real-time DB verification: validate membership status is ACTIVE
    if db is not None and not is_dev:
        from app.models.membership import MembershipStatus, UserOrganizationMembership

        user_id = current_user.get("id")
        check_org = str(target_org_id or user_org_id)
        if user_id and check_org:
            membership = (
                db.query(UserOrganizationMembership)  # type: ignore[union-attr]
                .filter(
                    UserOrganizationMembership.user_id == user_id,
                    UserOrganizationMembership.organization_id == check_org,
                )
                .first()
            )
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Membership in target organization does not exist or has been revoked",
                )
            if membership.status != MembershipStatus.ACTIVE.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Membership in target organization is {membership.status.lower()}",
                )
