"""Unit tests for Google OAuth 2.0 authentication endpoints."""

import time
import urllib.parse
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def test_google_login_redirect(client: TestClient):
    """GET /api/v1/auth/google/login should redirect to Google OAuth consent screen with CSRF cookie."""
    response = client.get("/api/v1/auth/google/login", follow_redirects=False)

    assert response.status_code == 302
    redirect_url = response.headers["location"]
    assert "https://accounts.google.com/o/oauth2/v2/auth" in redirect_url
    assert f"client_id={settings.GOOGLE_CLIENT_ID}" in redirect_url
    assert f"redirect_uri={urllib.parse.quote(settings.GOOGLE_OAUTH_REDIRECT_URI, safe='')}" in redirect_url
    assert "scope=openid+email+profile" in redirect_url or "scope=openid%20email%20profile" in redirect_url

    # Verify short-lived HttpOnly CSRF cookie is set
    cookies = response.headers.get("set-cookie", "").lower()
    assert "oauth_state_csrf=" in cookies
    assert "httponly" in cookies
    assert "samesite=lax" in cookies


def test_google_callback_with_error(client: TestClient):
    """GET /api/v1/auth/google/callback with error param should redirect to login page with error."""
    response = client.get("/api/v1/auth/google/callback?error=access_denied", follow_redirects=False)

    assert response.status_code == 302
    redirect_url = response.headers["location"]
    assert f"{settings.FRONTEND_URL}/login?auth_error=access_denied" in redirect_url


def test_google_callback_missing_code(client: TestClient):
    """GET /api/v1/auth/google/callback without code should redirect to frontend with missing code error."""
    response = client.get("/api/v1/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    redirect_url = response.headers["location"]
    assert "auth_error=missing_authorization_code" in redirect_url


@pytest.mark.asyncio
async def test_google_callback_success(client: TestClient):
    """Successful code exchange should retrieve userinfo, set session cookie, and redirect without token leakage."""
    from unittest.mock import MagicMock

    csrf_token = "valid-csrf-token-abc123"
    now = int(time.time())
    state_payload = {
        "csrf": csrf_token,
        "return_to": "/dashboard",
        "iat": now,
        "exp": now + 900,
    }
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "mock-google-access-token", "token_type": "Bearer"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-user-12345",
        "email": "developer@codeguard.ai",
        "name": "Alex Developer",
        "picture": "https://lh3.googleusercontent.com/a/mock-pic",
    }

    client.cookies.set("oauth_state_csrf", csrf_token)
    try:
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
        ):
            response = client.get(
                f"/api/v1/auth/google/callback?code=mock-auth-code&state={signed_state}",
                follow_redirects=False,
            )

        assert response.status_code == 302
        redirect_url = response.headers["location"]
        # Invariant: No token leakage in query parameters or fragments
        assert "token=" not in redirect_url
        assert redirect_url == f"{settings.FRONTEND_URL}/dashboard"

        # Invariant: HttpOnly session cookie is set
        set_cookies = response.headers.get("set-cookie", "")
        assert "codeguard_session=" in set_cookies
        assert "httponly" in set_cookies.lower()
    finally:
        client.cookies.clear()


def test_auth_me_with_bearer_jwt(client: TestClient):
    """GET /api/v1/auth/me should decode valid JWT and return user profile."""
    now = int(time.time())
    payload = {
        "iss": "codeguard-ai",
        "aud": "codeguard-api",
        "sub": "user-test-789",
        "email": "test@codeguard.ai",
        "name": "Test Engineer",
        "picture": "https://example.com/avatar.png",
        "role": "admin",
        "iat": now,
        "exp": now + 3600,
    }
    test_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {test_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["user"]["id"] == "user-test-789"
    assert data["user"]["login"] == "Test Engineer"
    assert data["user"]["email"] == "test@codeguard.ai"
    assert data["user"]["picture"] == "https://example.com/avatar.png"


def test_auth_logout_post_succeeds(client: TestClient):
    """POST /api/v1/auth/logout should return success and clear session cookies."""
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["success"] is True
    cookies = response.headers.get("set-cookie", "").lower()
    assert "codeguard_session=" in cookies
    assert "max-age=0" in cookies


def test_auth_logout_get_rejected(client: TestClient):
    """GET /api/v1/auth/logout must be rejected with 405 Method Not Allowed to eliminate Logout CSRF."""
    response = client.get("/api/v1/auth/logout")
    assert response.status_code == 405


def test_google_login_missing_client_id_raises_503(client: TestClient):
    """GET /api/v1/auth/google/login when GOOGLE_CLIENT_ID is not configured returns 503."""
    with patch.object(settings, "GOOGLE_CLIENT_ID", ""):
        response = client.get("/api/v1/auth/google/login", follow_redirects=False)
        assert response.status_code == 503
        assert "Google OAuth is not configured" in response.text


@pytest.mark.asyncio
async def test_google_callback_missing_server_credentials_redirects_unconfigured(client: TestClient):
    """GET /api/v1/auth/google/callback without GOOGLE_CLIENT_SECRET redirects to login with server_oauth_unconfigured."""
    csrf_token = "csrf-unconfigured-test"
    now = int(time.time())
    state_payload = {"csrf": csrf_token, "return_to": "/dashboard", "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    client.cookies.set("oauth_state_csrf", csrf_token)
    try:
        with patch.object(settings, "GOOGLE_CLIENT_SECRET", ""):
            response = client.get(
                f"/api/v1/auth/google/callback?code=mock-code&state={signed_state}",
                follow_redirects=False,
            )
            assert response.status_code == 302
            assert "auth_error=server_oauth_unconfigured" in response.headers["location"]
    finally:
        client.cookies.clear()


def test_auth_me_with_expired_session_fails(client: TestClient):
    """GET /api/v1/auth/me with an expired session token returns 401 Unauthorized."""
    past = int(time.time()) - 3600
    expired_payload = {
        "iss": "codeguard-ai",
        "aud": "codeguard-api",
        "sub": "user-expired-123",
        "email": "expired@codeguard.ai",
        "iat": past - 3600,
        "exp": past,
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm="HS256")

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert "Invalid or expired authentication token" in response.text


def test_auth_me_with_tampered_cookie_fails(client: TestClient):
    """GET /api/v1/auth/me with a tampered session cookie returns 401 Unauthorized."""
    with patch.object(settings, "DEV_AUTH_BYPASS", False):
        client.cookies.set("codeguard_session", "tampered.jwt.payload")
        try:
            response = client.get("/api/v1/auth/me")
            assert response.status_code == 401
            assert "Invalid or expired authentication token" in response.text
        finally:
            client.cookies.clear()


def test_auth_me_with_invalid_issuer_fails(client: TestClient):
    """GET /api/v1/auth/me with an invalid token issuer returns 401."""
    now = int(time.time())
    payload = {
        "iss": "untrusted-issuer",
        "aud": "codeguard-api",
        "sub": "user-bad-issuer",
        "iat": now,
        "exp": now + 3600,
    }
    bad_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert response.status_code == 401
    assert "Invalid token issuer" in response.text


@pytest.mark.asyncio
async def test_google_callback_with_active_organization_membership(client: TestClient, db_session):
    """Callback sets primary organization_id and organizations list when user has active memberships."""
    from unittest.mock import MagicMock

    from app.models.membership import MembershipRole, MembershipStatus, UserOrganizationMembership
    from app.models.organization import Organization
    from app.models.user import User

    # Pre-create organization and user with active membership
    org = Organization(
        github_installation_id=12345678,
        github_account_id=87654321,
        github_account_login="acme-corp",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    user = User(
        google_sub="google-org-user-sub",
        email="org-member@acme.com",
        name="Org Member",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    membership = UserOrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role=MembershipRole.MEMBER.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add(membership)
    db_session.commit()

    csrf_token = "csrf-org-member-token"
    now = int(time.time())
    state_payload = {"csrf": csrf_token, "return_to": "/dashboard", "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "token-org-member"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-org-user-sub",
        "email": "org-member@acme.com",
        "name": "Org Member",
    }

    client.cookies.set("oauth_state_csrf", csrf_token)
    try:
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
        ):
            response = client.get(
                f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
                follow_redirects=False,
            )

        assert response.status_code == 302
        cookie_header = response.headers.get("set-cookie", "")
        assert "codeguard_session=" in cookie_header

        # Extract and decode session cookie
        for cookie_part in cookie_header.split(";"):
            if "codeguard_session=" in cookie_part:
                token_val = cookie_part.split("codeguard_session=")[1].strip()
                decoded = jwt.decode(token_val, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
                assert decoded["organization_id"] == org.id
                assert org.id in decoded["organizations"]
                break
    finally:
        client.cookies.clear()


@pytest.mark.asyncio
async def test_google_callback_inactive_user_rejected(client: TestClient, db_session):
    """Callback rejects inactive user account with account_inactive redirect."""
    from unittest.mock import MagicMock

    from app.models.user import User

    inactive_user = User(
        google_sub="inactive-user-sub",
        email="inactive@example.com",
        name="Inactive User",
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()

    csrf_token = "csrf-inactive-token"
    now = int(time.time())
    state_payload = {"csrf": csrf_token, "return_to": "/dashboard", "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "token-inactive"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "inactive-user-sub",
        "email": "inactive@example.com",
        "name": "Inactive User",
    }

    client.cookies.set("oauth_state_csrf", csrf_token)
    try:
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
        ):
            response = client.get(
                f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "auth_error=account_inactive" in response.headers["location"]
    finally:
        client.cookies.clear()


@pytest.mark.asyncio
async def test_google_callback_secure_cookie_in_production(client: TestClient):
    """In production environment, session cookie sets Secure flag."""
    from unittest.mock import MagicMock

    csrf_token = "csrf-prod-cookie"
    now = int(time.time())
    state_payload = {"csrf": csrf_token, "return_to": "/dashboard", "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "token-prod"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "prod-user-sub",
        "email": "prod.user@codeguard.ai",
        "name": "Prod User",
    }

    client.cookies.set("oauth_state_csrf", csrf_token)
    try:
        with patch.object(settings, "APP_ENV", "production"), patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp
        ), patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp):
            response = client.get(
                f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
                follow_redirects=False,
            )

        assert response.status_code == 302
        cookies = response.headers.get("set-cookie", "").lower()
        assert "codeguard_session=" in cookies
        assert "secure" in cookies
        assert "httponly" in cookies
        assert "samesite=lax" in cookies
    finally:
        client.cookies.clear()

