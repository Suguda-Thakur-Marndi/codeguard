"""Unit tests for CodeGuard Configuration Validation (Phase 16 - Section 5)."""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_config_1_all_required_variables_present():
    """Verify default valid configuration initializes without errors."""
    cfg = Settings(
        APP_NAME="CodeGuard",
        APP_ENV="development",
        BACKEND_URL="http://localhost:8000",
        FRONTEND_URL="http://localhost:3000",
        DATABASE_URL="postgresql://user:pass@localhost:5432/db",
        REDIS_URL="redis://localhost:6379/0",
    )
    assert cfg.APP_NAME == "CodeGuard"
    assert cfg.BACKEND_URL == "http://localhost:8000"


def test_config_2_invalid_app_env():
    """Verify invalid literal value is rejected."""
    with pytest.raises(ValidationError) as exc:
        Settings(APP_ENV=cast(Any, "invalid_env"))
    assert "Input should be 'development', 'staging', 'production' or 'test'" in str(exc.value)


def test_config_3_invalid_log_level():
    """Verify invalid log level is rejected."""
    with pytest.raises(ValidationError) as exc:
        Settings(LOG_LEVEL=cast(Any, "TRACE"))
    assert "Input should be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'" in str(exc.value)


def test_config_4_malformed_url():
    """Verify malformed URL scheme or missing netloc is rejected."""
    with pytest.raises(ValidationError) as exc:
        Settings(BACKEND_URL="ftp://localhost:8000")
    assert "Invalid URL scheme 'ftp'" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        Settings(FRONTEND_URL="not_a_valid_url")
    assert "Invalid URL scheme ''" in str(exc.value) or "Malformed URL" in str(exc.value)


def test_config_5_invalid_port():
    """Verify out-of-range port is rejected."""
    with pytest.raises(ValidationError) as exc:
        Settings(BACKEND_URL="http://localhost:99999")
    assert "Invalid port" in str(exc.value) or "Port out of range" in str(exc.value) or "Malformed URL" in str(exc.value)


def test_config_6_invalid_database_configuration():
    """Verify unsupported or malformed database URL is rejected."""
    with pytest.raises(ValidationError) as exc:
        Settings(DATABASE_URL="mysql://root:pass@localhost:3306/db")
    assert "DATABASE_URL must start with a valid dialect prefix" in str(exc.value)


def test_config_7_invalid_gemini_configuration_production():
    """Verify production requires GEMINI_API_KEY and forbids mock provider."""
    # Mock LLM provider in production
    with pytest.raises(ValueError) as exc:
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql://prod_user:prod_pass@remote-db.internal:5432/prod_db",
            REDIS_URL="redis://remote-redis.internal:6379/0",
            BACKEND_URL="https://api.codeguard.internal",
            FRONTEND_URL="https://app.codeguard.internal",
            GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
            GITHUB_WEBHOOK_SECRET="secure_webhook_secret_32_bytes_long_here",
            SECRET_KEY="secure_session_secret_32_bytes_long_here",
            DEV_AUTH_BYPASS=False,
            LLM_PROVIDER="mock",
            GEMINI_API_KEY="AIzaSy_fake_test_key",
        )
    assert "LLM_PROVIDER cannot be 'mock' in production" in str(exc.value)

    # Missing GEMINI_API_KEY in production
    with pytest.raises(ValueError) as exc:
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql://prod_user:prod_pass@remote-db.internal:5432/prod_db",
            REDIS_URL="redis://remote-redis.internal:6379/0",
            BACKEND_URL="https://api.codeguard.internal",
            FRONTEND_URL="https://app.codeguard.internal",
            GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
            GITHUB_WEBHOOK_SECRET="secure_webhook_secret_32_bytes_long_here",
            SECRET_KEY="secure_session_secret_32_bytes_long_here",
            DEV_AUTH_BYPASS=False,
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="",
        )
    assert "GEMINI_API_KEY must be configured in production" in str(exc.value)


def test_config_8_invalid_github_configuration_production():
    """Verify production requires non-empty private key and non-default webhook secret."""
    with pytest.raises(ValueError) as exc:
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql://prod_user:prod_pass@remote-db.internal:5432/prod_db",
            REDIS_URL="redis://remote-redis.internal:6379/0",
            BACKEND_URL="https://api.codeguard.internal",
            FRONTEND_URL="https://app.codeguard.internal",
            GITHUB_PRIVATE_KEY="",
            GITHUB_WEBHOOK_SECRET="dev-webhook-secret",
            SECRET_KEY="secure_session_secret_32_bytes_long_here",
            DEV_AUTH_BYPASS=False,
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="AIzaSy_fake_test_key",
        )
    assert "GITHUB_PRIVATE_KEY must be configured in production" in str(exc.value)
    assert "Production GITHUB_WEBHOOK_SECRET must be configured" in str(exc.value)


def test_config_9_invalid_database_credentials_production():
    """Verify production rejects localhost or default credentials in DATABASE_URL."""
    with pytest.raises(ValueError) as exc:
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql://codeguard:codeguard_secret@localhost:5432/codeguard",
            REDIS_URL="redis://remote-redis.internal:6379/0",
            BACKEND_URL="https://api.codeguard.internal",
            FRONTEND_URL="https://app.codeguard.internal",
            GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
            GITHUB_WEBHOOK_SECRET="secure_webhook_secret_32_bytes_long_here",
            SECRET_KEY="secure_session_secret_32_bytes_long_here",
            DEV_AUTH_BYPASS=False,
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="AIzaSy_fake_test_key",
        )
    assert "Production DATABASE_URL must not use local default credentials" in str(exc.value)
