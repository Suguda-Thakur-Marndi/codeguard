# CodeGuard — Master Testing & Verification Guide

**Document ID**: `DOC-TEST-GUIDE-01`  
**Application Version**: `1.0.0`  
**Total Automated Tests**: 226 Pytest Tests  
**Last Verified Execution**: 2026-10-02  

---

## 1. Testing Philosophy & Test Pyramid

CodeGuard enforces strict unit, integration, and security test coverage across all subsystems:

- **Target Subsystems**: FastAPI routes, Pydantic schemas, Celery tasks, Tree-sitter parsers, Context ranker, Adversarial Judge, Zero-Trust Policy Engine, and Database repositories.

- **Zero-Weaken Axiom**: Tests are authoritative. If an existing test fails, the implementation must be fixed; assertions must never be suppressed, deleted, or loosened.
- **Mock vs. Live Testing Boundary**: Deterministic mock providers (`LLM_PROVIDER=mock`) and test fixtures are used in CI and local test harnesses to provide instant, reproducible verification without incurring cloud costs or relying on external internet availability.

---

## 2. Test Execution Commands & Verified Outcomes

### 2.1 Backend Unit & Integration Test Suites
Executes all unit and integration tests across the API backend.

```bash
# Run all 226 backend API tests
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
```
- **Target Subsystems**: FastAPI routes, Pydantic schemas, Celery tasks, Tree-sitter parsers, Context ranker, Adversarial Judge, Zero-Trust Policy Engine, and Database repositories.
- **Verified Outcome**: `226 passed` (`100% PASS, 0 FAIL`).

---

## 3. Code Quality, Linting & Type Analysis

### 3.1 Python Linting & Formatting (Ruff)
```bash
# Check code style, import sorting, and syntax rules
.\.venv\Scripts\ruff.exe check .

# Automatically apply safe formatting fixes
.\.venv\Scripts\ruff.exe format .
```
- **Configuration**: Target Python 3.11, line length 100 (`pyproject.toml`).
- **Verified Outcome**: `All checks passed!`.

### 3.2 Static Type Checking (Pyright)
```bash
# Verify static type safety on modified modules
npx --no-install pyright apps/api/tests/test_config.py
```
- **Configuration**: `pyrightconfig.json` with `.venv` execution path and monorepo extra paths.
- **Verified Outcome**: `0 errors, 0 warnings, 0 informations`.

### 3.3 Frontend Type Checking & Production Build (Next.js)
```bash
cd apps/web

# Check TypeScript validity
npm run lint

# Compile Next.js 15 standalone production bundle
npm run build
```
- **Verified Outcome**: 11 static and dynamic routes compiled; 0 TypeScript errors.

---

## 4. Continuous Integration (CI/CD) Workflows

The repository includes automated GitHub Actions workflows in `.github/workflows/`:

1. **`ci.yml`**:
   - Triggers on every push and pull request to `main`.
   - Matrix testing across Python 3.11, 3.12, 3.13.
   - Executes Ruff linting, Pytest test suites, and Next.js standalone build.
2. **`dependabot.yml`**:
   - Weekly automated security audits for Python (`pip`) and Node.js (`npm`) packages.

---

## 5. Known Test Limitations & Test Boundaries

1. **Simulated LLM Provider in Automated Tests**:
   - Tests run by default with `LLM_PROVIDER=mock` to ensure determinism and eliminate cloud API billing during test cycles.
   - Testing live Gemini model inference requires setting `LLM_PROVIDER=gemini` and providing an active `GEMINI_API_KEY`.
2. **Host Container Daemon Availability**:
   - Tests executing in local virtual environments validate AST-level execution sandboxes; kernel-level gVisor / seccomp container isolation requires running on a host with an active Linux Docker engine daemon.
3. **Absence of Real-World Customer Repositories**:
   - All acceptance and benchmark scenarios operate on synthetic test fixtures; testing on live customer repositories remains to be conducted during an authorized customer pilot.
