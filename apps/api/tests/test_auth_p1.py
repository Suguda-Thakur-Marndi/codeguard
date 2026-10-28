"""Regression tests for P1-B: Authentication security, dev bypass controls, OAuth state, and sessions."""

import time
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import is_safe_redirect_url
from app.core.config import Settings, settings
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


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


def test_google_login_generates_signed_jwt_state(client: TestClient):
    """Initiating Google OAuth generates signed JWT state with return_to and csrf nonce."""
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


def test_google_callback_tampered_state_rejected(client: TestClient):
    """Submitting tampered or invalid state to callback redirects to login with error."""
    response = client.get(
        "/api/v1/auth/google/callback?code=mock-code&state=tampered-or-expired-jwt",
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert f"{settings.FRONTEND_URL}/login?auth_error=invalid_oauth_state" in location


@pytest.mark.asyncio
async def test_google_callback_sets_session_cookie(client: TestClient):
    """Successful OAuth callback sets HttpOnly codeguard_session cookie and redirects."""
    now = int(time.time())
    state_payload = {
        "csrf": "csrf-nonce-12345",
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

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
    ):
        response = client.get(
            f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "/pull-requests?token=" in location

    # Verify HttpOnly session cookie
    cookies = response.headers.get_list("set-cookie") if hasattr(response.headers, "get_list") else [response.headers.get("set-cookie", "")]
    cookie_str = "; ".join(cookies)
    assert "codeguard_session=" in cookie_str
    assert "httponly" in cookie_str.lower()
    assert "samesite=lax" in cookie_str.lower()


def test_logout_clears_session_cookie(client: TestClient):
    """POST and GET /api/v1/auth/logout must clear the codeguard_session cookie."""
    # POST logout
    post_res = client.post("/api/v1/auth/logout")
    assert post_res.status_code == 200
    assert post_res.json()["success"] is True
    post_cookies = post_res.headers.get("set-cookie", "").lower()
    assert "codeguard_session=" in post_cookies
    assert "max-age=0" in post_cookies

    # GET logout
    get_res = client.get("/api/v1/auth/logout")
    assert get_res.status_code == 200
    assert get_res.json()["success"] is True
    get_cookies = get_res.headers.get("set-cookie", "").lower()
    assert "codeguard_session=" in get_cookies
    assert "max-age=0" in get_cookies
