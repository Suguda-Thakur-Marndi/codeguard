# CodeGuard — Configuration Audit & Variable Classification

This document provides a comprehensive audit of all configuration variables in CodeGuard, classifying each by security sensitivity, environment applicability, default values, and production validation rules.

---

## 1. Classification Categories

- **PUBLIC**: Safe for exposure in client-side bundles, status endpoints, and general documentation.
- **PRIVATE**: Internal infrastructure settings, timeouts, limits, or URLs. Must not be exposed in public clients.
- **SECRET**: Cryptographic keys, passwords, and API tokens. Must never be logged, committed to source control, or exposed in error messages.
- **ENVIRONMENT-SPECIFIC**: Settings that must be explicitly tailored between `development`, `staging`, and `production`.

---

## 2. Complete Configuration Inventory

| Variable Name | Classification | Type | Default Value | Production Requirement | Fail-Fast Validation Rule |
|---|---|---|---|---|---|
| `APP_NAME` | PUBLIC | `str` | `"CodeGuard"` | Optional | None |
| `APP_ENV` | ENVIRONMENT-SPECIFIC | `Literal` | `"development"` | Mandatory (`production`) | Must be one of `development`, `staging`, `production`, `test` |
| `LOG_LEVEL` | PUBLIC | `Literal` | `"INFO"` | Optional | Must be one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `DEBUG` | PUBLIC | `bool` | `False` | Must be `False` in prod | Disables interactive debug pages |
| `APP_VERSION` | PUBLIC | `str` | `"1.0.0"` | Release tag version | Injected during build |
| `GIT_REVISION` | PUBLIC | `str` | `"v1.0.0-release"` | Commit SHA / Tag | Injected during CI |
| `BACKEND_URL` | PRIVATE / ENV-SPECIFIC | `str` | `"http://localhost:8000"` | Production API FQDN | Valid URL |
| `FRONTEND_URL` | PRIVATE / ENV-SPECIFIC | `str` | `"http://localhost:3000"` | Production Web FQDN | Valid URL |
| `NEXT_PUBLIC_API_URL` | PUBLIC / ENV-SPECIFIC | `str` | `"http://localhost:8000/api/v1"` | Public API Gateway URL | Exclusively exposed to Next.js client |
| `DATABASE_URL` | SECRET / ENV-SPECIFIC | `str` | `"postgresql://..."` | Production PostgreSQL URI with SSL | Cannot contain `localhost` or default password `codeguard_secret` |
| `POSTGRES_USER` | PRIVATE / ENV-SPECIFIC | `str` | `"codeguard"` | Production DB user | Alphanumeric |
| `POSTGRES_PASSWORD` | SECRET | `str` | `"codeguard_secret"` | Strong generated password | Non-default in prod |
| `POSTGRES_DB` | PRIVATE / ENV-SPECIFIC | `str` | `"codeguard"` | Database name | Valid DB identifier |
| `DB_POOL_SIZE` | PRIVATE | `int` | `10` (20 in prod) | 20 | Minimum connection pool size |
| `DB_MAX_OVERFLOW` | PRIVATE | `int` | `20` (40 in prod) | 40 | Maximum overflow connections |
| `DB_POOL_TIMEOUT` | PRIVATE | `int` | `30` | 30 | Seconds to wait before connection timeout |
| `REDIS_URL` | SECRET / ENV-SPECIFIC | `str` | `"redis://localhost:6379/0"` | Production Redis URI with auth | Valid Redis URL with password in prod |
| `REDIS_PASSWORD` | SECRET | `str` | `""` | Generated strong secret | Required when Redis password auth is active |
| `GITHUB_APP_ID` | PRIVATE / ENV-SPECIFIC | `str` | `"dev-app-id"` | Production GitHub App ID | Must not be empty in prod |
| `GITHUB_CLIENT_ID` | PUBLIC / ENV-SPECIFIC | `str` | `"dev-client-id"` | Production GitHub Client ID | OAuth application client ID |
| `GITHUB_CLIENT_SECRET` | SECRET | `str` | `"dev-client-secret"` | Production GitHub Client Secret | OAuth token exchange secret |
| `GITHUB_WEBHOOK_SECRET` | SECRET | `str` | `"dev-webhook-secret"` | Strong generated secret | Must not be empty or `"dev-webhook-secret"` in prod |
| `GITHUB_PRIVATE_KEY` | SECRET | `str` | `""` | RSA Private Key in PEM format | Required in prod; validated for non-empty string |
| `IGNORE_DRAFT_PRS` | PRIVATE | `bool` | `False` | `False` | Skips review on draft PRs if `True` |
| `CELERY_TASK_ALWAYS_EAGER` | PRIVATE / ENV-SPECIFIC | `bool` | `False` | Must be `False` in prod | If `True`, Celery runs synchronously (test mode only) |
| `GEMINI_API_KEY` | SECRET | `str` | `""` | Valid Google Gemini API Key | Required in prod; validated for non-empty string |
| `LLM_PROVIDER` | PRIVATE / ENV-SPECIFIC | `Literal` | `"gemini"` | Must be `"gemini"` in prod | Cannot be `"mock"` in production |
| `GEMINI_MODEL_FAST` | PRIVATE | `str` | `"gemini-2.5-flash"` | `"gemini-2.5-flash"` | Model routing for high-throughput comprehension |
| `GEMINI_MODEL_REASONING` | PRIVATE | `str` | `"gemini-2.5-pro"` | `"gemini-2.5-pro"` | Model routing for complex security analysis |
| `AGENT_MAX_CONCURRENCY` | PRIVATE | `int` | `4` | `4` | Max concurrent specialist LLM executions |
| `AGENT_MAX_RETRIES` | PRIVATE | `int` | `2` | `2` | Bounded retries for transient LLM errors |
| `AGENT_TIMEOUT_SECONDS` | PRIVATE | `float` | `60.0` | `60.0` | Execution timeout per agent step |
| `MAX_CONTEXT_CHARS` | PRIVATE | `int` | `16000` | `16000` | Maximum character budget per prompt |
| `MAX_CONTEXT_FILES` | PRIVATE | `int` | `10` | `10` | Maximum files included in diff context |
| `MAX_CONTEXT_SYMBOLS` | PRIVATE | `int` | `30` | `30` | Maximum AST symbol references included |
| `APPROVAL_EXPIRY_MINUTES_DEFAULT`| PRIVATE | `int` | `60` | `60` | Window before human approval expires |
| `DEV_AUTH_BYPASS` | PRIVATE / ENV-SPECIFIC | `bool` | `True` (dev only) | Must be `False` in prod | Fail-fast validation crashes if `True` in production |
| `DEV_AUTH_TOKEN` | PRIVATE | `str` | `"codeguard-dev-token"` | Empty in prod | Bypass token for local tests |
| `SECRET_KEY` | SECRET | `str` | `"insecure-dev..."` | 32+ byte cryptographically random hex | Cannot start with `"insecure-dev"` in prod |
| `CORS_ORIGINS` | PRIVATE / ENV-SPECIFIC | `list[str]` | `["http://localhost:3000"]` | Whitelisted production FQDNs | Wildcard `*` is strictly forbidden in production |

---

## 3. Production Fail-Fast Validation Contract

The configuration engine in `apps/api/app/core/config.py` enforces fail-fast assertions during application boot (`Settings.model_post_init`):

```python
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
        raise ValueError(f"Production configuration validation failed: {'; '.join(errors)}")
```

Any violation halts application startup immediately with an explicit error list, preventing partially configured or insecure instances from serving traffic.
