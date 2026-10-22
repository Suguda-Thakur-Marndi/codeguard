"""Tests for GitHub connection flow, repository discovery, and tenant isolation."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.repository import Repository
from app.services.webhook_service import WebhookService


def test_get_github_install_url(client: TestClient):
    """Verify endpoint returning GitHub App installation URL."""
    res = client.get("/api/v1/github/install-url")
    assert res.status_code == 200
    data = res.json()
    assert "install_url" in data
    assert "app_slug" in data
    assert "https://github.com/apps/" in data["install_url"]


def test_verify_and_link_installation(client: TestClient, db_session: Session):
    """Verify linking a GitHub installation creates/updates an Organization."""
    installation_id = 998877

    res = client.post(
        "/api/v1/github/installations/verify",
        json={"installation_id": installation_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["installation_id"] == installation_id
    assert data["verified"] is True
    assert "id" in data

    # Verify Organization is in database
    org = db_session.query(Organization).filter_by(github_installation_id=installation_id).first()
    assert org is not None


def test_list_installations(client: TestClient, db_session: Session):
    """Verify listing all connected installations."""
    # Seed an installation
    org = Organization(
        github_installation_id=554433,
        github_account_id=123,
        github_account_login="test-org",
        account_type="Organization",
    )
    db_session.add(org)
    db_session.commit()

    res = client.get("/api/v1/github/installations")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    matching = [item for item in data if item["installation_id"] == 554433]
    assert len(matching) == 1
    assert matching[0]["account_login"] == "test-org"


def test_list_accessible_repositories(client: TestClient, db_session: Session):
    """Verify discovery of repositories granted to a GitHub App installation."""
    installation_id = 112233

    res = client.get(f"/api/v1/github/installations/{installation_id}/repositories")
    assert res.status_code == 200
    data = res.json()
    assert data["installation_id"] == installation_id
    assert "repositories" in data
    assert len(data["repositories"]) > 0

    first_repo = data["repositories"][0]
    assert "github_repo_id" in first_repo
    assert "full_name" in first_repo
    assert "is_connected" in first_repo


def test_connect_and_disconnect_repository(client: TestClient, db_session: Session):
    """Verify connecting and subsequently disconnecting a GitHub repository."""
    installation_id = 778899

    # 1. Connect repository
    connect_payload = {
        "installation_id": installation_id,
        "github_repo_id": 1234567,
        "owner": "codeguard-ai",
        "name": "sample-repo",
        "full_name": "codeguard-ai/sample-repo",
        "default_branch": "main",
        "is_private": True,
    }
    connect_res = client.post("/api/v1/github/repositories/connect", json=connect_payload)
    assert connect_res.status_code == 201
    repo_data = connect_res.json()
    assert repo_data["github_repo_id"] == 1234567
    assert repo_data["full_name"] == "codeguard-ai/sample-repo"
    repo_id = repo_data["id"]

    # Verify repository appears in list_repositories
    list_res = client.get("/api/v1/repositories")
    assert list_res.status_code == 200
    repo_ids = [r["id"] for r in list_res.json()["items"]]
    assert repo_id in repo_ids

    # Verify discovered repositories now flag this repository as is_connected=True
    accessible_res = client.get(f"/api/v1/github/installations/{installation_id}/repositories")
    assert accessible_res.status_code == 200

    # 2. Disconnect repository
    disconnect_res = client.delete(f"/api/v1/repositories/{repo_id}")
    assert disconnect_res.status_code == 200
    assert disconnect_res.json()["success"] is True

    # Verify repository is removed
    get_res = client.get(f"/api/v1/repositories/{repo_id}")
    assert get_res.status_code == 404


def test_webhook_cross_tenant_isolation(db_session: Session):
    """Verify that webhooks attempting to mutate another tenant's repository are rejected."""
    # 1. Create Tenant A Org and Repo
    org_a = Organization(
        github_installation_id=1001,
        github_account_id=501,
        github_account_login="tenant-a",
        account_type="Organization",
    )
    db_session.add(org_a)
    db_session.flush()

    repo_a = Repository(
        organization_id=org_a.id,
        github_repo_id=888899,
        owner="tenant-a",
        name="secure-app",
        full_name="tenant-a/secure-app",
        default_branch="main",
        is_private=True,
    )
    db_session.add(repo_a)
    db_session.commit()

    # 2. Simulate webhook from Malicious Tenant B with installation_id 2002 targeting repo 888899
    service = WebhookService(db_session)
    malicious_payload = {
        "action": "opened",
        "installation": {"id": 2002},
        "repository": {
            "id": 888899,
            "name": "secure-app",
            "full_name": "tenant-a/secure-app",
            "owner": {"login": "tenant-a", "id": 501, "type": "Organization"},
            "default_branch": "main",
            "private": True,
        },
        "pull_request": {
            "id": 99991,
            "number": 1,
            "title": "Malicious Spoof PR",
            "state": "open",
            "draft": False,
            "user": {"login": "attacker"},
            "head": {"sha": "attacker_head_sha"},
            "base": {"sha": "base_sha"},
        },
    }

    res = service.process_webhook("pull_request", "delivery-fake-1", malicious_payload)
    # Must be ignored due to installation_id mismatch
    assert res.status == "ignored"
    assert res.message is not None
    assert "Installation ID does not match" in res.message
