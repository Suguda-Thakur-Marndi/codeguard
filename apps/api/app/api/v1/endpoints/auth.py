"""Authentication endpoints: Google OAuth 2.0 and session management."""

import hmac
import secrets
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.core.security import get_current_user_or_bypass
from app.db.session import get_db
from app.models.membership import MembershipStatus, UserOrganizationMembership
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def is_safe_redirect_url(url: str | None) -> bool:
    """Ensure return URL is an internal relative path preventing open redirects."""
    if not url:
        return False
    # Reject scheme-relative (//), Windows backslash (\), and absolute URLs with schemes (:)
    if url.startswith("//") or "\\" in url or ":" in url:
        return False
    return url.startswith("/")


@router.get("/google/login", summary="Initiate Google OAuth 2.0 login flow")
async def google_login(redirect_url: str | None = Query(None)) -> RedirectResponse:
    """Redirect user to Google's OAuth 2.0 consent screen with state bound to CSRF cookie."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured. Missing GOOGLE_CLIENT_ID.",
        )

    # Encode safe return destination and CSRF nonce in signed state JWT
    safe_return = redirect_url if is_safe_redirect_url(redirect_url) else "/dashboard"
    now = datetime.now(UTC)
    csrf_nonce = secrets.token_urlsafe(32)
    state_payload = {
        "csrf": csrf_nonce,
        "return_to": safe_return,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state,
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    logger.info("Redirecting user to Google OAuth consent screen with CSRF state cookie.")
    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)

    # Bind OAuth state to initiating client browser via short-lived HttpOnly cookie
    is_secure = settings.APP_ENV in ("production", "staging")
    response.set_cookie(
        key="oauth_state_csrf",
        value=csrf_nonce,
        max_age=15 * 60,  # 15 minutes matching JWT expiration
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/google/callback", summary="Google OAuth 2.0 callback handler")
async def google_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle Google OAuth 2.0 authorization code callback with state cookie binding and session security."""
    frontend_base = settings.FRONTEND_URL.rstrip("/")

    def _error_redirect(err_code: str) -> RedirectResponse:
        res = RedirectResponse(
            url=f"{frontend_base}/login?auth_error={urllib.parse.quote(err_code)}",
            status_code=status.HTTP_302_FOUND,
        )
        res.delete_cookie("oauth_state_csrf", path="/")
        return res

    if error:
        logger.warning(f"Google OAuth returned error: {error}")
        return _error_redirect(error)

    if not code:
        logger.error("Google OAuth callback missing authorization code.")
        return _error_redirect("missing_authorization_code")

    if not state:
        logger.error("Google OAuth callback missing state parameter.")
        return _error_redirect("missing_oauth_state")

    # 1. Verify CSRF cookie binding to mitigate Login CSRF
    cookie_csrf = request.cookies.get("oauth_state_csrf")
    if not cookie_csrf:
        logger.warning("Missing OAuth CSRF cookie in callback request.")
        return _error_redirect("missing_oauth_cookie")

    # 2. Validate signed state JWT and constant-time compare CSRF token
    target_destination = "/dashboard"
    try:
        state_data = jwt.decode(
            state,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "csrf"]},
        )
        state_csrf = state_data.get("csrf")
        if not state_csrf or not hmac.compare_digest(str(cookie_csrf), str(state_csrf)):
            logger.warning("OAuth state CSRF token mismatch between cookie and state payload.")
            return _error_redirect("invalid_oauth_state")

        return_path = state_data.get("return_to")
        if return_path and is_safe_redirect_url(return_path):
            target_destination = return_path
    except Exception as exc:
        logger.warning(f"Invalid or expired OAuth state parameter: {exc}")
        return _error_redirect("invalid_oauth_state")

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        logger.error("Google OAuth client credentials not configured on server.")
        return _error_redirect("server_oauth_unconfigured")

    # 3. Exchange authorization code for Google access token
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )

            if token_resp.status_code != 200:
                err_detail = token_resp.text
                logger.error(f"Failed to exchange Google OAuth code for token: {err_detail}")
                return _error_redirect("token_exchange_failed")

            token_data = token_resp.json()
            access_token = token_data.get("access_token")

            if not access_token:
                logger.error("No access_token returned by Google token endpoint.")
                return _error_redirect("no_access_token")

            # Retrieve user identity info from Google
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if userinfo_resp.status_code != 200:
                logger.error(f"Failed to fetch userinfo from Google: {userinfo_resp.text}")
                return _error_redirect("userinfo_fetch_failed")

            user_data = userinfo_resp.json()

    except Exception as exc:
        logger.error(f"Exception during Google OAuth callback processing: {exc}", exc_info=True)
        return _error_redirect("oauth_network_error")

    # 4. Resolve persistent User record
    raw_email = user_data.get("email", "")
    norm_email = raw_email.strip().lower()
    raw_sub = user_data.get("sub") or norm_email
    name = user_data.get("name") or (norm_email.split("@")[0] if norm_email else "Google User")
    picture = user_data.get("picture")

    if not norm_email or not raw_sub:
        logger.error("Incomplete identity payload returned by Google userinfo endpoint.")
        return _error_redirect("invalid_identity_payload")

    user = (
        db.query(User)
        .filter((User.google_sub == raw_sub) | (User.email == norm_email))
        .first()
    )

    if not user:
        user = User(
            google_sub=raw_sub,
            email=norm_email,
            name=name,
            picture=picture,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Keep user profile synced with Google profile
        updated = False
        if not user.google_sub:
            user.google_sub = raw_sub
            updated = True
        if name and user.name != name:
            user.name = name
            updated = True
        if picture and user.picture != picture:
            user.picture = picture
            updated = True
        if not user.is_active:
            logger.warning(f"Inactive user account '{norm_email}' attempted Google OAuth login.")
            return _error_redirect("account_inactive")
        if updated:
            db.commit()
            db.refresh(user)

    # 5. Retrieve verified active organization memberships
    # Invariant: Do NOT automatically grant organization membership based on email domain,
    # Google sign-in alone, or client-supplied org ID.
    memberships = (
        db.query(UserOrganizationMembership)
        .filter(
            UserOrganizationMembership.user_id == user.id,
            UserOrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        .all()
    )
    active_org_ids = [m.organization_id for m in memberships]
    primary_org_id = active_org_ids[0] if active_org_ids else None

    # 6. Issue signed CodeGuard JWT session token with user subject and organization claims
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=7)

    payload = {
        "iss": "codeguard-ai",
        "aud": "codeguard-api",
        "sub": user.id,
        "google_sub": raw_sub,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": "developer",
        "organization_id": primary_org_id,
        "organizations": active_org_ids,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    session_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    logger.info(f"Successfully authenticated user '{norm_email}' (id: {user.id}) via Google OAuth.")

    # 5. Redirect strictly to destination without exposing token in query string or fragment
    redirect_target = f"{frontend_base}{target_destination}"
    response = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)

    # Invalidate CSRF state cookie upon consumption to prevent replay attacks
    response.delete_cookie("oauth_state_csrf", path="/")

    # Set secure HttpOnly session cookie
    is_secure = settings.APP_ENV in ("production", "staging")
    response.set_cookie(
        key="codeguard_session",
        value=session_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me", summary="Get authenticated user details")
async def get_current_user_profile(
    response: Response,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user_or_bypass),
) -> dict[str, Any]:
    """Return profile details for current authenticated session and refresh active org claims."""
    user_id = current_user.get("id")
    if user_id and not current_user.get("is_dev"):
        memberships = (
            db.query(UserOrganizationMembership)
            .filter(
                UserOrganizationMembership.user_id == user_id,
                UserOrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
            .all()
        )
        active_org_ids = [m.organization_id for m in memberships]
        if active_org_ids and (not current_user.get("organization_id") or not current_user.get("organizations")):
            primary_org_id = active_org_ids[0]
            current_user["organization_id"] = primary_org_id
            current_user["organizations"] = active_org_ids

            now = datetime.now(UTC)
            expires_at = now + timedelta(days=7)
            payload = {
                "iss": "codeguard-ai",
                "aud": "codeguard-api",
                "sub": user_id,
                "email": current_user.get("email"),
                "name": current_user.get("login"),
                "picture": current_user.get("picture"),
                "role": current_user.get("role", "developer"),
                "organization_id": primary_org_id,
                "organizations": active_org_ids,
                "iat": int(now.timestamp()),
                "exp": int(expires_at.timestamp()),
            }
            session_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
            is_secure = settings.APP_ENV in ("production", "staging")
            response.set_cookie(
                key="codeguard_session",
                value=session_token,
                max_age=7 * 24 * 3600,
                httponly=True,
                secure=is_secure,
                samesite="lax",
                path="/",
            )

    return {
        "authenticated": True,
        "user": current_user,
    }


@router.post("/logout", summary="Logout current session")
async def logout(response: Response) -> dict[str, Any]:
    """Stateless logout confirmation and cookie clearing restricted to POST."""
    is_secure = settings.APP_ENV in ("production", "staging")
    response.delete_cookie(
        "codeguard_session",
        path="/",
        secure=is_secure,
        httponly=True,
        samesite="lax",
    )
    return {
        "success": True,
        "message": "Logged out successfully",
    }
