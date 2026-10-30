# CodeGuard — Developer Setup & Local Environment Guide

**Document ID**: `DOC-SETUP-01`  
**Application Version**: `1.0.0`  
**Target Environments**: Local Developer Workstation (Windows, Linux, macOS)  
**Last Verified**: 2026-09-29  

---

## 1. System Requirements & Runtime Matrix

Before setting up CodeGuard, ensure your system meets the following prerequisite versions:

| Component | Minimum Version | Recommended Version | Verification Command |
| :--- | :--- | :--- | :--- |
| **Python** | `>= 3.11.0` | `3.12` or `3.13` | `python --version` |
| **Node.js** | `>= 20.0.0` | `22.x LTS` | `node --version` |
| **npm** | `>= 10.0.0` | `10.8+` | `npm --version` |
| **Git** | `>= 2.40.0` | Latest | `git --version` |
| **PostgreSQL** *(Optional for local test; required for prod/staging)* | `15.0+` | `16.x` | `psql --version` |
| **Redis** *(Optional for local eager test; required for prod/staging)* | `6.2+` | `7.x` | `redis-cli --version` |
| **Docker & Docker Compose** *(Optional for local venv development)* | `24.0+` | Latest | `docker compose version` |

*Note: For rapid local testing and unit tests, CodeGuard supports SQLite in-memory / local files and Celery eager execution (`CELERY_TASK_ALWAYS_EAGER=true`), eliminating the mandatory need for active local Postgres/Redis daemons.*

---

## 2. Step-by-Step Local Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/Suguda-Thakur-Marndi/codeguard-ai.git
cd codeguard-ai
```

### Step 2: Set Up Python Virtual Environment
Create and activate an isolated Python virtual environment at the repository root:

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

**On Linux / macOS (Bash/Zsh):**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Step 3: Install Python Monorepo Packages in Editable Mode
Install the code intelligence package and API with development dependencies:
```bash
pip install -e "./packages/code-intelligence" -e "./apps/api[dev]"
```

Verify that all packages are installed cleanly without dependency conflicts:
```bash
pip list | grep -E "codeguard|fastapi|pydantic|tree-sitter"
```

### Step 4: Install Frontend Node Dependencies
Navigate to the Next.js web application and install npm dependencies:
```bash
cd apps/web
npm install
cd ../..
```

---

## 3. Environment Variable Configuration

CodeGuard utilizes Pydantic Settings (`app.core.config.Settings`) with strict fail-fast validation.

### Step 1: Initialize Local Environment File
```bash
cp .env.example .env
```

### Step 2: Environment Variable Template & Reference

| Variable Name | Required | Environment | Default / Safe Placeholder | Description |
| :--- | :---: | :---: | :--- | :--- |
| **`APP_NAME`** | Yes | All | `CodeGuard` | Display name of the application |
| **`APP_ENV`** | Yes | All | `development` (`development`, `staging`, `production`, `test`) | Runtime operational mode |
| **`DEBUG`** | No | Dev | `true` | Enables verbose stack traces and debug routes |
| **`LOG_LEVEL`** | No | All | `INFO` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) | Log severity threshold |
| **`BACKEND_URL`** | Yes | All | `http://localhost:8000` | Fully qualified backend URL |
| **`FRONTEND_URL`** | Yes | All | `http://localhost:3000` | Fully qualified frontend dashboard URL |
| **`DATABASE_URL`** | Yes | All | `sqlite:///./local.db` *(or `postgresql://user:pass@localhost:5432/codeguard`)* | Database connection URI |
| **`REDIS_URL`** | Yes | All | `redis://localhost:6379/0` | Redis task queue and cache broker |
| **`SECRET_KEY`** | Yes | All | `dev-secret-key-change-in-production-min-32-chars` | JWT cryptographic signing key |
| **`DEV_AUTH_BYPASS`** | No | Dev Only | `true` *(Strictly rejected if `APP_ENV=production`)* | Allows bypass of JWT auth in local development |
| **`CELERY_TASK_ALWAYS_EAGER`** | No | Dev/Test | `true` *(Set to `false` when running Celery worker daemon)* | Executes tasks synchronously inline |
| **`LLM_PROVIDER`** | Yes | All | `mock` *(Use `gemini` for live model inference)* | AI model provider engine |
| **`GEMINI_API_KEY`** | Conditional | Prod/Staging | `your_gemini_api_key_here` | Required only when `LLM_PROVIDER=gemini` |
| **`GEMINI_MODEL_FAST`** | No | All | `gemini-2.5-flash` | Fast specialist model |
| **`GEMINI_MODEL_REASONING`**| No | All | `gemini-2.5-pro` | Deep reasoning & Adversarial Judge model |
| **`GITHUB_APP_ID`** | Conditional | Prod/Staging | `12345` | GitHub App numerical ID |
| **`GITHUB_PRIVATE_KEY`** | Conditional | Prod/Staging | `""` *(PEM-encoded RSA key)* | Required for live GitHub API authentication |
| **`GITHUB_WEBHOOK_SECRET`** | Conditional | Prod/Staging | `dev-webhook-secret-token` | Secret for HMAC-SHA256 signature verification |

---

## 4. Database Initialization & Migrations

CodeGuard uses **Alembic** to manage 27 relational tables across 6 sequential revisions.

### Apply Migrations to HEAD:
```bash
# From repository root:
alembic -c apps/api/alembic.ini upgrade head
```

Verify migration status:
```bash
alembic -c apps/api/alembic.ini current
```
*Expected output*: `006_phase7_benchmarking_tables (head)`

---

## 5. Starting the Application Services Locally

To run the complete system locally for development, open separate terminal windows for each process:

### Terminal 1: Backend REST API (`:8000`)
```powershell
.\.venv\Scripts\uvicorn app.main:app --app-dir apps/api --reload --port 8000
```
- **Liveness Probe**: `curl http://localhost:8000/api/v1/live` $\rightarrow$ `{"status": "ok"}`
- **Readiness Probe**: `curl http://localhost:8000/api/v1/ready` $\rightarrow$ `{"status": "ok", "database": true}`
- **Swagger Documentation**: Open `http://localhost:8000/docs` in your browser.

### Terminal 2: Celery Background Review Worker (When not in eager mode)
```powershell
.\.venv\Scripts\celery.exe -A app.workers.celery_app worker --loglevel=info --pool=solo
```
*(On Linux/macOS, omit `--pool=solo`)*.

### Terminal 3: Next.js Frontend Dashboard (`:3000`)
```bash
cd apps/web
npm run dev
```
- **Dashboard Interface**: Open `http://localhost:3000` in your browser.

---

## 6. Verifying the Local Installation

Run the complete automated test suite to ensure your local environment is 100% operational:

```powershell
# 1. Run all Pytest backend unit & integration tests
.\.venv\Scripts\python.exe -m pytest apps/api/tests -v

# 2. Run Ruff linter and static code check
.\.venv\Scripts\ruff.exe check .

# 3. Check frontend build
cd apps\web
npm run lint
npm run build
cd ..\..
```

---

## 7. Common Local Setup Issues & Solutions

### Issue 1: `ModuleNotFoundError: No module named 'tree_sitter'`
- **Cause**: Packages were not installed in editable mode within the active virtual environment.
- **Solution**: Run `pip install -e "./packages/code-intelligence" -e "./apps/api[dev]"`.

### Issue 2: `ValueError: DEV_AUTH_BYPASS cannot be True in production`
- **Cause**: `.env` contains `APP_ENV=production` while `DEV_AUTH_BYPASS=true`.
- **Solution**: For local development, set `APP_ENV=development` in your `.env` file.

### Issue 3: Celery Worker Hangs on Windows
- **Cause**: Celery defaults to `prefork` process pooling, which is unsupported on Windows.
- **Solution**: Always append `--pool=solo` or `--pool=threads` when launching Celery on Windows:
  `celery -A app.workers.celery_app worker --pool=solo -l info`. Alternatively, set `CELERY_TASK_ALWAYS_EAGER=true` in `.env` for synchronous inline execution.

### Issue 4: Next.js Build Warning regarding React 19 / ESLint
- **Cause**: ESLint 9 flat-config migration compatibility warnings.
- **Solution**: Run `npm run lint` inside `apps/web`; the Next.js standalone build compiles cleanly with zero TypeScript errors via `npm run build`.
