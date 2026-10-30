"""Regression tests for P1-B: Authentication security, dev bypass controls, OAuth state, and sessions."""

import time
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import is_safe_redirect_url
from app.core.config import Settings, settings

# ---------------------------------------------------------------------------
# 1. DEV_AUTH_BYPASS Default & Environment Enforcement
# ---------------------------------------------------------------------------


def test_dev_auth_bypass_default_is_false(monkeypatch):
    """Verify that DEV_AUTH_BYPASS defaults to False in clean settings."""
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    s = Settings(
        _env_file=None,
        APP_ENV="test",
        SECRET_KEY="test-secret-key-that-is-at-least-32-bytes-long",
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="password",
        POSTGRES_DB="test_db",
    )
    assert s.DEV_AUTH_BYPASS is False


def test_dev_auth_bypass_forbidden_in_production():
    """Enabling DEV_AUTH_BYPASS in production must raise ValueError."""
    with pytest.raises(ValueError, match="DEV_AUTH_BYPASS cannot be True in 'production'"):
        Settings(
            APP_ENV="production",
            DEV_AUTH_BYPASS=True,
            SECRET_KEY="production-secret-key-at-least-32-bytes-long",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="postgres",
            POSTGRES_PASSWORD="password",
            POSTGRES_DB="prod_db",
        )


def test_dev_auth_bypass_forbidden_in_staging():
    """Enabling DEV_AUTH_BYPASS in staging must raise ValueError."""
    with pytest.raises(ValueError, match="DEV_AUTH_BYPASS cannot be True in 'staging'"):
        Settings(
            APP_ENV="staging",
            DEV_AUTH_BYPASS=True,
            SECRET_KEY="staging-secret-key-at-least-32-bytes-long",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="postgres",
            POSTGRES_PASSWORD="password",
            POSTGRES_DB="staging_db",
        )


def test_dev_auth_bypass_forbidden_in_unknown_environment():
    """Enabling DEV_AUTH_BYPASS in an unknown environment must fail validation."""
    with pytest.raises((ValueError, Exception), match="Input should be 'development', 'staging', 'production' or 'test'"):
        Settings(
            APP_ENV="custom_cloud",
            DEV_AUTH_BYPASS=True,
            SECRET_KEY="custom-secret-key-at-least-32-bytes-long",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="postgres",
            POSTGRES_PASSWORD="password",
            POSTGRES_DB="custom_db",
        )


def test_dev_auth_bypass_allowed_in_development_and_test():
    """DEV_AUTH_BYPASS can only be enabled in development or test."""
    dev_settings = Settings(
        APP_ENV="development",
        DEV_AUTH_BYPASS=True,
        SECRET_KEY="dev-secret-key-at-least-32-bytes-long",
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="password",
        POSTGRES_DB="dev_db",
    )
    assert dev_settings.DEV_AUTH_BYPASS is True

    test_settings = Settings(
        APP_ENV="test",
        DEV_AUTH_BYPASS=True,
        SECRET_KEY="test-secret-key-at-least-32-bytes-long",
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="password",
        POSTGRES_DB="test_db",
    )
    assert test_settings.DEV_AUTH_BYPASS is True


# ---------------------------------------------------------------------------
# 2. Unauthenticated and Dev Token Handling when Bypass is Disabled
# ---------------------------------------------------------------------------


def test_unauthenticated_request_rejected_when_bypass_false(client: TestClient):
    """When DEV_AUTH_BYPASS is False, unauthenticated requests must return 401."""
    with patch.object(settings, "DEV_AUTH_BYPASS", False):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert "Authentication credentials required" in response.text


def test_dev_token_rejected_when_bypass_false(client: TestClient):
    """When DEV_AUTH_BYPASS is False, X-Dev-Token must return 401."""
    with patch.object(settings, "DEV_AUTH_BYPASS", False):
        response = client.get(
            "/api/v1/auth/me",
            headers={"X-Dev-Token": "codeguard-dev-token"},
        )
        assert response.status_code == 401
        assert "Development token is disabled" in response.text


def test_valid_session_cookie_accepted(client: TestClient):
    """When DEV_AUTH_BYPASS is False, a valid codeguard_session cookie is accepted."""
    now = int(time.time())
    payload = {
        "iss": "codeguard-ai",
        "aud": "codeguard-api",
        "sub": "cookie-user-42",
        "email": "cookie.user@codeguard.ai",
        "name": "Cookie User",
        "role": "developer",
        "iat": now,
        "exp": now + 3600,
    }
    session_jwt = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    with patch.object(settings, "DEV_AUTH_BYPASS", False):
        client.cookies.set("codeguard_session", session_jwt)
        try:
            response = client.get("/api/v1/auth/me")
            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is True
            assert data["user"]["id"] == "cookie-user-42"
            assert data["user"]["email"] == "cookie.user@codeguard.ai"
        finally:
            client.cookies.clear()


# ---------------------------------------------------------------------------
# 3. Open Redirect Prevention & State Security
# ---------------------------------------------------------------------------


def test_is_safe_redirect_url_validation():
    """Verify internal relative paths are accepted and open-redirect vectors rejected."""
    # Safe internal relative paths
    assert is_safe_redirect_url("/dashboard") is True
    assert is_safe_redirect_url("/repositories") is True
    assert is_safe_redirect_url("/pull-requests/42?tab=findings") is True

    # Dangerous open-redirect attempts
    assert is_safe_redirect_url(None) is False
    assert is_safe_redirect_url("") is False
    assert is_safe_redirect_url("https://attacker.com") is False
    assert is_safe_redirect_url("http://attacker.com/dashboard") is False
    assert is_safe_redirect_url("//attacker.com") is False
    assert is_safe_redirect_url("\\attacker.com") is False
    assert is_safe_redirect_url("/\\attacker.com") is False
    assert is_safe_redirect_url("javascript:alert(1)") is False


def test_google_login_generates_signed_jwt_state_and_csrf_cookie(client: TestClient):
    """Initiating Google OAuth generates signed JWT state and binds it to a short-lived CSRF cookie."""
    response = client.get("/api/v1/auth/google/login?redirect_url=/repositories", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]

    parsed = urllib.parse.urlparse(location)
    query_params = urllib.parse.parse_qs(parsed.query)

    assert "state" in query_params
    raw_state = query_params["state"][0]

    # Verify state is signed with server secret
    decoded = jwt.decode(raw_state, settings.SECRET_KEY, algorithms=["HS256"])
    assert "csrf" in decoded
    assert len(decoded["csrf"]) > 10
    assert decoded["return_to"] == "/repositories"
    assert "exp" in decoded

    # Invariant: Initiating browser receives HttpOnly CSRF cookie matching the state token
    cookie_str = response.headers.get("set-cookie", "")
    assert "oauth_state_csrf=" in cookie_str
    assert "httponly" in cookie_str.lower()
    assert "samesite=lax" in cookie_str.lower()


def test_google_login_sanitizes_unsafe_redirect_url(client: TestClient):
    """Initiating Google OAuth with an external redirect sanitizes it to /dashboard."""
    response = client.get(
        "/api/v1/auth/google/login?redirect_url=https://evil.example.com",
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]

    parsed = urllib.parse.urlparse(location)
    query_params = urllib.parse.parse_qs(parsed.query)
    raw_state = query_params["state"][0]

    decoded = jwt.decode(raw_state, settings.SECRET_KEY, algorithms=["HS256"])
    assert decoded["return_to"] == "/dashboard"


def test_google_callback_missing_csrf_cookie_rejected(client: TestClient):
    """Callback request without the oauth_state_csrf cookie must be rejected (Login CSRF defense)."""
    now = int(time.time())
    state_payload = {"csrf": "valid-token-12345", "return_to": "/dashboard", "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    # Do not set cookie in client
    client.cookies.clear()
    response = client.get(
        f"/api/v1/auth/google/callback?code=mock-code&state={signed_state}",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=missing_oauth_cookie" in response.headers["location"]


def test_google_callback_mismatched_csrf_cookie_rejected(client: TestClient):
    """Callback with mismatched CSRF cookie and state token must be rejected."""
    now = int(time.time())
    state_payload = {"csrf": "original-csrf-nonce", "return_to": "/dashboard", "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    client.cookies.set("oauth_state_csrf", "attacker-injected-cookie-value")
    try:
        response = client.get(
            f"/api/v1/auth/google/callback?code=mock-code&state={signed_state}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "auth_error=invalid_oauth_state" in response.headers["location"]
    finally:
        client.cookies.clear()


def test_google_callback_tampered_state_rejected(client: TestClient):
    """Submitting tampered or invalid state to callback redirects to login with error."""
    client.cookies.set("oauth_state_csrf", "some-cookie")
    try:
        response = client.get(
            "/api/v1/auth/google/callback?code=mock-code&state=tampered-or-expired-jwt",
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert f"{settings.FRONTEND_URL}/login?auth_error=invalid_oauth_state" in location
    finally:
        client.cookies.clear()


@pytest.mark.asyncio
async def test_google_callback_sets_session_cookie_and_no_token_leakage(client: TestClient):
    """Successful OAuth callback sets HttpOnly session cookie, clears CSRF cookie, and does NOT leak token in URL."""
    csrf_nonce = "verified-session-binding-csrf-nonce"
    now = int(time.time())
    state_payload = {
        "csrf": csrf_nonce,
        "return_to": "/pull-requests",
        "iat": now,
        "exp": now + 900,
    }
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "mock-access-token", "token_type": "Bearer"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-user-999",
        "email": "reviewer@codeguard.ai",
        "name": "Code Reviewer",
        "picture": "https://lh3.googleusercontent.com/avatar.png",
    }

    client.cookies.set("oauth_state_csrf", csrf_nonce)
    try:
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
        ):
            response = client.get(
                f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
                follow_redirects=False,
            )

        assert response.status_code == 302
        location = response.headers["location"]
        # Invariant: No token in query params, fragments, or path
        assert "token=" not in location
        assert location == f"{settings.FRONTEND_URL}/pull-requests"

        # Invariant: HttpOnly session cookie is established
        cookies_header = response.headers.get("set-cookie", "")
        assert "codeguard_session=" in cookies_header
        assert "httponly" in cookies_header.lower()
        assert "samesite=lax" in cookies_header.lower()

        # Invariant: oauth_state_csrf is cleared to prevent replay attacks
        assert "oauth_state_csrf=" in cookies_header
        assert "max-age=0" in cookies_header.lower()
    finally:
        client.cookies.clear()


def test_logout_restricted_to_post_and_clears_cookie(client: TestClient):
    """POST /auth/logout must clear codeguard_session cookie, and GET must be rejected with 405."""
    # 1. POST logout succeeds
    post_res = client.post("/api/v1/auth/logout")
    assert post_res.status_code == 200
    assert post_res.json()["success"] is True
    post_cookies = post_res.headers.get("set-cookie", "").lower()
    assert "codeguard_session=" in post_cookies
    assert "max-age=0" in post_cookies

    # 2. GET logout is rejected with 405 Method Not Allowed to eliminate Logout CSRF
    get_res = client.get("/api/v1/auth/logout")
    assert get_res.status_code == 405


# ---------------------------------------------------------------------------
# 4. Multi-Tenant Grounding for Google OAuth Principals
# ---------------------------------------------------------------------------


def test_google_authenticated_user_without_org_denied_tenant_access(client: TestClient):
    """Google OAuth authenticated user with no organization membership is denied access to tenant resources."""
    now = int(time.time())
    payload = {
        "iss": "codeguard-ai",
        "aud": "codeguard-api",
        "sub": "google-user-no-org",
        "email": "external@gmail.com",
        "name": "External User",
        "role": "developer",
        "organization_id": None,  # No verified org membership
        "iat": now,
        "exp": now + 3600,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    # Accessing an organization's specific policy without verified membership -> 403 Forbidden
    response = client.get(
        "/api/v1/organizations/org-alpha-999/policies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "No verified organization membership" in response.text or "forbidden" in response.text.lower()


def test_google_authenticated_user_with_verified_org_allowed_and_cross_denied(client: TestClient):
    """Google OAuth user with verified organization_id can access own tenant, but is denied other tenants."""
    now = int(time.time())
    payload = {
        "iss": "codeguard-ai",
        "aud": "codeguard-api",
        "sub": "google-user-with-org",
        "email": "employee@company.com",
        "name": "Company Employee",
        "role": "developer",
        "organization_id": "org-company-123",
        "iat": now,
        "exp": now + 3600,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    # Cross-tenant request to a different organization -> 403 Forbidden
    cross_res = client.get(
        "/api/v1/organizations/org-competitor-456/policies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cross_res.status_code == 403
    assert "Cross-tenant access forbidden" in cross_res.text
