"""Tests for health and readiness probes."""

import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Verify liveness probe returns HTTP 200 with status ok."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    from app.core.config import settings
    assert data["status"] == "ok"
    assert data["app"] == settings.APP_NAME
    assert data["version"] == settings.APP_VERSION


def test_root_endpoint(client: TestClient) -> None:
    """Verify root / returns API metadata and endpoints."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "CodeGuard" in data["name"]
    assert data["phase"] == "Phase 1 - Production Foundation"


def test_readiness_check_all_healthy(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify /ready returns 200 when both DB and Redis are connected."""
    monkeypatch.setattr("app.api.v1.endpoints.health.check_db_connectivity", lambda: True)
    monkeypatch.setattr("app.api.v1.endpoints.health.check_redis_connectivity", lambda: True)

    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["postgres"] == "connected"
    assert data["redis"] == "connected"


def test_readiness_check_degraded_when_db_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify /ready returns HTTP 503 when database is disconnected."""
    monkeypatch.setattr("app.api.v1.endpoints.health.check_db_connectivity", lambda: False)
    monkeypatch.setattr("app.api.v1.endpoints.health.check_redis_connectivity", lambda: True)

    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["postgres"] == "disconnected"
    assert data["redis"] == "connected"


def test_readiness_check_degraded_when_redis_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify /ready returns HTTP 503 when Redis is disconnected."""
    monkeypatch.setattr("app.api.v1.endpoints.health.check_db_connectivity", lambda: True)
    monkeypatch.setattr("app.api.v1.endpoints.health.check_redis_connectivity", lambda: False)

    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["postgres"] == "connected"
    assert data["redis"] == "disconnected"
