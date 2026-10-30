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
