"""Pytest fixtures for database, test client, and mock services."""

import hashlib
import hmac
import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Force testing configuration
os.environ["APP_ENV"] = "test"
os.environ["GITHUB_APP_ID"] = "dev-app-id"
os.environ["GITHUB_PRIVATE_KEY_PATH"] = ""
os.environ["GITHUB_PRIVATE_KEY"] = ""
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret-for-unit-tests"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long"
os.environ["DEV_AUTH_BYPASS"] = "true"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["REDIS_URL"] = "memory://"
os.environ["LLM_PROVIDER"] = "mock"

from app.core.config import settings  # noqa: E402

settings.LLM_PROVIDER = "mock"

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

# In-memory SQLite engine for fast, isolated unit test execution
TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    """Create test database schema before tests and drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional database session rolled back after every test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def mock_celery_task_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Celery delay call so tests do not require a live Redis instance."""
    from app.workers import tasks
    monkeypatch.setattr(tasks.process_review_job, "delay", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.publish_review_task, "delay", lambda *args, **kwargs: None)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden database dependency."""
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_webhook_signature(body: bytes, secret: str = "test-webhook-secret-for-unit-tests") -> str:
    """Generate X-Hub-Signature-256 header value for given payload bytes."""
    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@pytest.fixture
def sample_pr_payload() -> dict:
    """Standard GitHub pull_request opened webhook payload fixture."""
    return {
        "action": "opened",
        "number": 101,
        "pull_request": {
            "id": 55443322,
            "number": 101,
            "title": "Fix memory leak in buffer pool",
            "body": "Resolves issue where buffer was not dereferenced upon socket close.",
            "state": "open",
            "draft": False,
            "user": {"login": "octocat", "id": 1},
            "base": {
                "sha": "1111111111111111111111111111111111111111",
                "ref": "main",
            },
            "head": {
                "sha": "2222222222222222222222222222222222222222",
                "ref": "fix/buffer-leak",
            },
        },
        "repository": {
            "id": 998877,
            "name": "core-engine",
            "full_name": "acme/core-engine",
            "private": True,
            "default_branch": "main",
            "owner": {
                "id": 4455,
                "login": "acme",
                "type": "Organization",
            },
        },
        "installation": {
            "id": 123456,
        },
    }
