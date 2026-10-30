"""Application configuration using Pydantic Settings."""

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with production validation."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Environment & Logging
    APP_NAME: str = "CodeGuard"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    DEBUG: bool = False

    # URLs
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    # Build & Release Versioning
    APP_VERSION: str = "1.0.0"
    GIT_REVISION: str = "v1.0.0-release"

    # Database & Redis
    DATABASE_URL: str = "postgresql://codeguard:codeguard@localhost:5432/codeguard"
    REDIS_URL: str = "redis://localhost:6379/0"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # GitHub App Credentials & Installation URLs
    GITHUB_APP_ID: str = "dev-app-id"
    GITHUB_APP_SLUG: str = "codeguard-ai-123"
    GITHUB_APP_CLIENT_ID: str = ""
    GITHUB_APP_INSTALL_URL: str = ""
    GITHUB_PRIVATE_KEY: str = ""
    GITHUB_PRIVATE_KEY_PATH: str = ""
    GITHUB_WEBHOOK_SECRET: str = "dev-webhook-secret"
    GITHUB_CLIENT_ID: str = "dev-client-id"
    GITHUB_CLIENT_SECRET: str = "dev-client-secret"

    # Google OAuth 2.0 Credentials
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # Review Job & Webhook Settings
    IGNORE_DRAFT_PRS: bool = False
    CELERY_TASK_ALWAYS_EAGER: bool = False  # Set to True for synchronous testing

    # Phase 3: AI Agent & LLM Provider Configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_FAST: str = "gemini-2.5-flash"
    GEMINI_MODEL_REASONING: str = "gemini-2.5-pro"
    LLM_PROVIDER: Literal["gemini", "mock"] = "gemini"

    # Agent Execution Boundaries & Concurrency
    AGENT_MAX_CONCURRENCY: int = 4
    AGENT_MAX_RETRIES: int = 2
    AGENT_TIMEOUT_SECONDS: float = 60.0
    MAX_CONTEXT_CHARS: int = 16000
    MAX_CONTEXT_FILES: int = 10
    MAX_CONTEXT_SYMBOLS: int = 30

    # Model Routing Configuration (maps specialist to fast vs reasoning tier)
    MODEL_TIER_COMPREHENSION: Literal["fast", "reasoning"] = "fast"
    MODEL_TIER_SECURITY: Literal["fast", "reasoning"] = "reasoning"
    MODEL_TIER_BUG: Literal["fast", "reasoning"] = "reasoning"
    MODEL_TIER_TEST: Literal["fast", "reasoning"] = "fast"
    MODEL_TIER_PERFORMANCE: Literal["fast", "reasoning"] = "reasoning"

    # Token Pricing (USD per 1,000,000 tokens)
    PRICE_PER_MILLION_INPUT_TOKENS_FAST: float = 0.075
    PRICE_PER_MILLION_OUTPUT_TOKENS_FAST: float = 0.30
    PRICE_PER_MILLION_INPUT_TOKENS_REASONING: float = 1.25
    PRICE_PER_MILLION_OUTPUT_TOKENS_REASONING: float = 5.00

    # Phase 4: Adversarial Verification & Execution Sandbox Configuration
    SANDBOX_IMAGE: str = "codeguard-sandbox:latest"
    SANDBOX_CPU_LIMIT: float = 1.0
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_MAX_PROCESSES: int = 64
    SANDBOX_TIMEOUT_SECONDS: int = 30
    SANDBOX_MAX_OUTPUT_BYTES: int = 65536
    MAX_CONCURRENT_VALIDATIONS: int = 4
    SANDBOX_ALLOWLIST_COMMANDS: list[str] = [
        "pytest",
        "python -m pytest",
        "npm test",
        "npm run test",
        "ruff check",
        "eslint",
    ]
    STATIC_ANALYZERS_ENABLED: list[str] = ["ruff", "eslint"]
    JUDGE_MODEL_TIER: Literal["fast", "reasoning"] = "reasoning"
    JUDGE_MAX_RETRIES: int = 2

    # Human Approval Configuration
    APPROVAL_EXPIRY_MINUTES_DEFAULT: int = 60

    # Security & Auth
    DEV_AUTH_BYPASS: bool = False
    DEV_AUTH_TOKEN: str = "codeguard-dev-token"
    SECRET_KEY: str = "insecure-dev-secret-key-change-in-production-32bytes"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(i) for i in v]
        return ["http://localhost:3000"]

    @field_validator("BACKEND_URL", "FRONTEND_URL")
    @classmethod
    def validate_service_urls(cls, v: str) -> str:
        if not v:
            raise ValueError("URL cannot be empty")
        try:
            parsed = urlparse(v)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"Invalid URL scheme '{parsed.scheme}'; must be 'http' or 'https'")
            if not parsed.netloc:
                raise ValueError("URL must include a valid host/network location")
            if parsed.port is not None and not (1 <= parsed.port <= 65535):
                raise ValueError(f"Invalid port '{parsed.port}'; must be between 1 and 65535")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Malformed URL: {e}") from e
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL cannot be empty")
        valid_prefixes = (
            "postgresql://",
            "postgresql+psycopg2://",
            "postgresql+asyncpg://",
            "sqlite://",
            "sqlite+aiosqlite://",
        )
        if not any(v.startswith(prefix) for prefix in valid_prefixes):
            raise ValueError("DATABASE_URL must start with a valid dialect prefix (e.g. postgresql://, sqlite://)")
        return v

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not v:
            raise ValueError("REDIS_URL cannot be empty")
        if not (v.startswith("redis://") or v.startswith("rediss://") or v.startswith("memory://")):
            raise ValueError("REDIS_URL must start with redis://, rediss://, or memory://")
        return v

    def model_post_init(self, __context: object) -> None:
        """Validate production invariants and resolve file-based credentials."""
        # 1. Resolve GITHUB_PRIVATE_KEY from GITHUB_PRIVATE_KEY_PATH if path provided and key is empty
        if not self.GITHUB_PRIVATE_KEY and self.GITHUB_PRIVATE_KEY_PATH:
            candidate_paths = [
                self.GITHUB_PRIVATE_KEY_PATH,
                os.path.abspath(self.GITHUB_PRIVATE_KEY_PATH),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), self.GITHUB_PRIVATE_KEY_PATH),
            ]
            for p in candidate_paths:
                if os.path.isfile(p):
                    try:
                        with open(p, encoding="utf-8") as f:
                            self.GITHUB_PRIVATE_KEY = f.read().strip()
                        break
                    except Exception:
                        pass

        # 2. Sync GITHUB_APP_CLIENT_ID and GITHUB_CLIENT_ID
        if self.GITHUB_APP_CLIENT_ID and self.GITHUB_CLIENT_ID in ("", "dev-client-id"):
            self.GITHUB_CLIENT_ID = self.GITHUB_APP_CLIENT_ID
        elif self.GITHUB_CLIENT_ID and not self.GITHUB_APP_CLIENT_ID and self.GITHUB_CLIENT_ID != "dev-client-id":
            self.GITHUB_APP_CLIENT_ID = self.GITHUB_CLIENT_ID

        # 3. Environment validation & fail-closed security invariants
        if self.DEV_AUTH_BYPASS and self.APP_ENV not in ("development", "test"):
            raise ValueError(
                f"DEV_AUTH_BYPASS cannot be True in '{self.APP_ENV}' environment. "
                "Development authentication bypass is strictly forbidden outside development and test environments."
            )

        if self.APP_ENV == "staging":
            if self.DEV_AUTH_BYPASS:
                raise ValueError("DEV_AUTH_BYPASS cannot be True in staging.")

        if self.APP_ENV == "production":
            errors = []
            if "*" in self.CORS_ORIGINS:
                errors.append("Wildcard CORS (*) is forbidden in production.")
            if not self.GITHUB_PRIVATE_KEY:
                errors.append("GITHUB_PRIVATE_KEY must be configured in production.")
            if self.GITHUB_WEBHOOK_SECRET in ("dev-webhook-secret", ""):
                errors.append("Production GITHUB_WEBHOOK_SECRET must be configured.")
            if self.SECRET_KEY.startswith("insecure-dev"):
                errors.append("Production SECRET_KEY must be securely configured.")
            if self.DEV_AUTH_BYPASS:
                errors.append("DEV_AUTH_BYPASS cannot be True in production.")
            if self.LLM_PROVIDER == "mock":
                errors.append("LLM_PROVIDER cannot be 'mock' in production.")
            if not self.GEMINI_API_KEY:
                errors.append("GEMINI_API_KEY must be configured in production.")
            if "localhost" in self.DATABASE_URL or "codeguard_secret" in self.DATABASE_URL:
                errors.append("Production DATABASE_URL must not use local default credentials or localhost.")
            if errors:
                raise ValueError(
                    f"Production configuration validation failed: {'; '.join(errors)}"
                )

    @property
    def github_app_install_url(self) -> str:
        """Resolve GitHub App installation URL."""
        if self.GITHUB_APP_INSTALL_URL:
            return self.GITHUB_APP_INSTALL_URL
        slug = self.GITHUB_APP_SLUG or "codeguard-ai"
        return f"https://github.com/apps/{slug}/installations/new"


settings = Settings()
