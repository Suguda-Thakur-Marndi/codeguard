"""Comprehensive regression tests for Organization Membership schema and authorization integration.

Verifies:
1. User creation and lookup on Google OAuth login (normalized email, stable google_sub).
2. Existing user sync and inactive user rejection.
3. Active membership retrieval and embedding into session JWT (sub = user.id).
4. No automatic membership grant based on email domain or Google sign-in alone.
5. Users without membership can access /auth/me and /health, but receive 403 on org-scoped endpoints.
6. Multi-tenant access control and cross-tenant denial.
7. Real-time membership revocation/suspension fails closed even with unexpired JWT claims.
8. Migration upgrade and downgrade execution.
"""

import os
import tempfile
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import settings
from app.models.membership import (
    MembershipRole,
    MembershipStatus,
    UserOrganizationMembership,
)
from app.models.organization import Organization
from app.models.repository import Repository
from app.models.user import User


def _create_jwt(payload_override: dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "iss": "codeguard-ai",
        "aud": "codeguard-api",
        "sub": "test-user-id",
        "email": "test@example.com",
        "name": "Test User",
        "role": "developer",
        "organization_id": None,
        "organizations": [],
        "iat": now,
        "exp": now + 3600,
    }
    payload.update(payload_override)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


# ===========================================================================
# 1. Google OAuth User Lookup, Creation & Membership Integration
# ===========================================================================


@pytest.mark.asyncio
async def test_oauth_creates_new_user_and_reads_memberships(client: TestClient, db_session: Session):
    """Google OAuth login creates persistent User and embeds memberships in session JWT."""
    # Seed an Organization and pre-assigned active membership
    org = Organization(
        github_installation_id=987654,
        github_account_id=12345,
        github_account_login="acme-corp",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.flush()

    csrf_token = "valid-csrf-nonce"
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
    mock_token_resp.json.return_value = {"access_token": "mock-token", "token_type": "Bearer"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-sub-999",
        "email": "  Alice.Engineer@Acme.COM  ",  # Un-normalized
        "name": "Alice Engineer",
        "picture": "https://example.com/alice.png",
    }

    client.cookies.set("oauth_state_csrf", csrf_token)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
    ):
        resp = client.get(
            f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert "token=" not in resp.headers["location"]

    # Verify user was created with normalized email and stable google_sub
    user = db_session.query(User).filter(User.google_sub == "google-sub-999").first()
    assert user is not None
    assert user.email == "alice.engineer@acme.com"
    assert user.name == "Alice Engineer"
    assert user.picture == "https://example.com/alice.png"
    assert user.is_active is True

    # Check issued session token
    session_cookie = resp.cookies.get("codeguard_session")
    assert session_cookie is not None
    token_claims = jwt.decode(
        session_cookie,
        settings.SECRET_KEY,
        algorithms=["HS256"],
        options={"require": ["exp", "sub"], "verify_aud": False},
    )
    assert token_claims["sub"] == user.id
    assert token_claims["google_sub"] == "google-sub-999"
    assert token_claims["email"] == "alice.engineer@acme.com"
    # User had no pre-existing membership
    assert token_claims["organization_id"] is None
    assert token_claims["organizations"] == []


@pytest.mark.asyncio
async def test_oauth_existing_user_membership_embedding(client: TestClient, db_session: Session):
    """Existing user with active memberships receives organization claims in session JWT."""
    org = Organization(
        github_installation_id=55555,
        github_account_id=66666,
        github_account_login="mega-corp",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.flush()

    user = User(
        google_sub="google-sub-existing",
        email="bob@megacorp.com",
        name="Bob Mega",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    membership = UserOrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role=MembershipRole.ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add(membership)
    db_session.commit()

    csrf_token = "csrf-bob-123"
    now = int(time.time())
    state_payload = {"csrf": csrf_token, "return_to": "/dashboard", "iat": now, "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "mock-token", "token_type": "Bearer"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-sub-existing",
        "email": "bob@megacorp.com",
        "name": "Bob Mega Updated",
        "picture": "https://example.com/bob_new.png",
    }

    client.cookies.set("oauth_state_csrf", csrf_token)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
    ):
        resp = client.get(
            f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
            follow_redirects=False,
        )

    assert resp.status_code == 302

    # Verify user profile updated without duplicate row
    db_session.refresh(user)
    assert user.name == "Bob Mega Updated"
    assert user.picture == "https://example.com/bob_new.png"

    # Verify token claims include the active organization
    session_cookie = resp.cookies.get("codeguard_session")
    token_claims = jwt.decode(
        session_cookie,
        settings.SECRET_KEY,
        algorithms=["HS256"],
        options={"require": ["exp", "sub"], "verify_aud": False},
    )
    assert token_claims["sub"] == user.id
    assert token_claims["organization_id"] == org.id
    assert org.id in token_claims["organizations"]


@pytest.mark.asyncio
async def test_oauth_inactive_user_rejected(client: TestClient, db_session: Session):
    """Deactivated user cannot log in via Google OAuth."""
    user = User(
        google_sub="google-sub-inactive",
        email="inactive@company.com",
        name="Inactive Person",
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    csrf_token = "csrf-inactive-123"
    now = int(time.time())
    state_payload = {"csrf": csrf_token, "return_to": "/dashboard", "iat": now, "exp": now + 900}
    signed_state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "mock-token", "token_type": "Bearer"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-sub-inactive",
        "email": "inactive@company.com",
    }

    client.cookies.set("oauth_state_csrf", csrf_token)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp), patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_resp
    ):
        resp = client.get(
            f"/api/v1/auth/google/callback?code=valid-code&state={signed_state}",
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert "auth_error=account_inactive" in resp.headers["location"]


# ===========================================================================
# 2. Authorization Enforcement: Users Without Membership
# ===========================================================================


def test_user_without_membership_allowed_on_personal_endpoints(client: TestClient, db_session: Session):
    """Users without memberships can access personal endpoints (/auth/me, /health)."""
    user = User(
        google_sub="google-sub-ungrounded",
        email="ungrounded@example.com",
        name="Ungrounded User",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    token = _create_jwt({
        "sub": user.id,
        "email": user.email,
        "organization_id": None,
        "organizations": [],
    })
    headers = {"Authorization": f"Bearer {token}"}

    # /auth/me succeeds
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["id"] == user.id
    assert me_resp.json()["user"]["organization_id"] is None

    # /health succeeds
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200


def test_user_without_membership_denied_on_org_scoped_endpoints(client: TestClient, db_session: Session):
    """Users without memberships receive 403 Forbidden on org-scoped resources."""
    user = User(
        google_sub="google-sub-nomember",
        email="nomember@example.com",
        name="No Member User",
        is_active=True,
    )
    org = Organization(
        github_installation_id=121212,
        github_account_id=343434,
        github_account_login="target-org",
        account_type="Organization",
    )
    db_session.add_all([user, org])
    db_session.flush()

    repo = Repository(
        organization_id=org.id,
        github_repo_id=99999,
        owner="target-org",
        name="secure-repo",
        full_name="target-org/secure-repo",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.commit()

    token = _create_jwt({
        "sub": user.id,
        "email": user.email,
        "organization_id": None,
        "organizations": [],
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Repositories list denied
    r1 = client.get("/api/v1/repositories", headers=headers)
    assert r1.status_code == 403
    assert "No verified organization membership" in r1.json()["detail"]

    # Specific repository access denied
    r2 = client.get(f"/api/v1/repositories/{repo.id}", headers=headers)
    assert r2.status_code == 403
    assert "No verified organization membership" in r2.json()["detail"]

    # Pull requests list denied
    r3 = client.get("/api/v1/pull-requests", headers=headers)
    assert r3.status_code == 403
    assert "No verified organization membership" in r3.json()["detail"]

    # Organizations list returns empty for ungrounded user
    r4 = client.get("/api/v1/organizations", headers=headers)
    assert r4.status_code == 200
    assert r4.json()["total"] == 0
    assert r4.json()["items"] == []


# ===========================================================================
# 3. Real-Time Revocation & Suspension
# ===========================================================================


def test_real_time_revocation_and_suspension_fails_closed(client: TestClient, db_session: Session):
    """Membership status changes in DB immediately fail closed even with valid JWT claims."""
    org = Organization(
        github_installation_id=444111,
        github_account_id=222111,
        github_account_login="secure-tenant",
        account_type="Organization",
    )
    user = User(
        google_sub="google-sub-realtime",
        email="realtime@company.com",
        name="Realtime User",
        is_active=True,
    )
    db_session.add_all([org, user])
    db_session.flush()

    membership = UserOrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role=MembershipRole.MEMBER.value,
        status=MembershipStatus.ACTIVE.value,
    )
    repo = Repository(
        organization_id=org.id,
        github_repo_id=777666,
        owner="secure-tenant",
        name="repo-1",
        full_name="secure-tenant/repo-1",
        default_branch="main",
    )
    db_session.add_all([membership, repo])
    db_session.commit()

    token = _create_jwt({
        "sub": user.id,
        "email": user.email,
        "organization_id": org.id,
        "organizations": [org.id],
    })
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Access permitted while ACTIVE
    resp_active = client.get(f"/api/v1/repositories/{repo.id}", headers=headers)
    assert resp_active.status_code == 200
    assert resp_active.json()["id"] == repo.id

    # 2. Suspend membership in database
    membership.status = MembershipStatus.SUSPENDED.value
    db_session.commit()

    # Access immediately denied (403 Forbidden)
    resp_suspended = client.get(f"/api/v1/repositories/{repo.id}", headers=headers)
    assert resp_suspended.status_code == 403
    assert "suspended" in resp_suspended.json()["detail"].lower()

    # 3. Revoke (delete) membership in database
    db_session.delete(membership)
    db_session.commit()

    # Access immediately denied (403 Forbidden)
    resp_revoked = client.get(f"/api/v1/repositories/{repo.id}", headers=headers)
    assert resp_revoked.status_code == 403
    assert "revoked" in resp_revoked.json()["detail"].lower() or "does not exist" in resp_revoked.json()["detail"].lower()


# ===========================================================================
# 4. Multi-Organization Access & Cross-Tenant Denial
# ===========================================================================


def test_multi_organization_membership(client: TestClient, db_session: Session):
    """User with multiple active memberships can access permitted orgs, but is denied on unjoined orgs."""
    org1 = Organization(
        github_installation_id=111001,
        github_account_id=222001,
        github_account_login="org-one",
        account_type="Organization",
    )
    org2 = Organization(
        github_installation_id=111002,
        github_account_id=222002,
        github_account_login="org-two",
        account_type="Organization",
    )
    org3 = Organization(
        github_installation_id=111003,
        github_account_id=222003,
        github_account_login="org-three",
        account_type="Organization",
    )
    user = User(
        google_sub="google-sub-multiorg",
        email="multi@corp.com",
        name="Multi Org User",
        is_active=True,
    )
    db_session.add_all([org1, org2, org3, user])
    db_session.flush()

    # Active in Org 1 and Org 2, not Org 3
    m1 = UserOrganizationMembership(
        user_id=user.id,
        organization_id=org1.id,
        role=MembershipRole.OWNER.value,
        status=MembershipStatus.ACTIVE.value,
    )
    m2 = UserOrganizationMembership(
        user_id=user.id,
        organization_id=org2.id,
        role=MembershipRole.MEMBER.value,
        status=MembershipStatus.ACTIVE.value,
    )
    repo1 = Repository(
        organization_id=org1.id,
        github_repo_id=888001,
        owner="org-one",
        name="service-1",
        full_name="org-one/service-1",
        default_branch="main",
    )
    repo2 = Repository(
        organization_id=org2.id,
        github_repo_id=888002,
        owner="org-two",
        name="service-2",
        full_name="org-two/service-2",
        default_branch="main",
    )
    repo3 = Repository(
        organization_id=org3.id,
        github_repo_id=888003,
        owner="org-three",
        name="service-3",
        full_name="org-three/service-3",
        default_branch="main",
    )
    db_session.add_all([m1, m2, repo1, repo2, repo3])
    db_session.commit()

    token = _create_jwt({
        "sub": user.id,
        "email": user.email,
        "organization_id": org1.id,
        "organizations": [org1.id, org2.id],
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Org 1 access allowed
    resp1 = client.get(f"/api/v1/repositories/{repo1.id}", headers=headers)
    assert resp1.status_code == 200

    # Org 2 access allowed
    resp2 = client.get(f"/api/v1/repositories/{repo2.id}", headers=headers)
    assert resp2.status_code == 200

    # Org 3 access strictly denied (Cross-tenant access forbidden)
    resp3 = client.get(f"/api/v1/repositories/{repo3.id}", headers=headers)
    assert resp3.status_code == 403
    assert "Cross-tenant access forbidden" in resp3.json()["detail"]

    # Organizations list returns exactly Org 1 and Org 2
    orgs_resp = client.get("/api/v1/organizations", headers=headers)
    assert orgs_resp.status_code == 200
    listed_org_ids = [o["id"] for o in orgs_resp.json()["items"]]
    assert org1.id in listed_org_ids
    assert org2.id in listed_org_ids
    assert org3.id not in listed_org_ids


# ===========================================================================
# 5. Alembic Migration Upgrade and Downgrade Execution
# ===========================================================================


def test_alembic_migration_007_upgrade_downgrade():
    """Verify revision 007 applies schema cleanly and downgrades back to 006."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        cfg = Config("apps/api/alembic.ini")
        cfg.set_main_option("script_location", "apps/api/alembic")

        # Upgrade to head
        command.upgrade(cfg, "head")

        # Downgrade back to 006
        command.downgrade(cfg, "006_phase7_benchmarking_tables")

        # Upgrade back to head
        command.upgrade(cfg, "head")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
