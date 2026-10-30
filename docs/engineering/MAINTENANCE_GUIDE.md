# CodeGuard — Long-Term Maintenance & Upgrade Guide

**Document Status**: Active / Authoritative  
**Date**: September 17, 2026  
**Target Audience**: DevOps, Backend, AI & Platform Engineers

---

## 1. Overview & Golden Invariants

When modifying, maintaining, or upgrading CodeGuard, engineers must preserve the following architectural invariants:
1. **Never Bypass Human Authorization**: Consequential actions (publishing reviews, modifying external resources) require authenticated human approval.
2. **Never Weaken Tests**: If a test fails after an upgrade, the upgrade is defective or incompatible. Fix the implementation or revert the upgrade.
3. **Never Redesign Frontend UI/UX**: Visual styling, components, colors, and layouts in `apps/web/` must remain preserved.
4. **Never Commit Secrets**: Ensure all environment configs use placeholders and all telemetry scrubs credentials.

---

## 2. Dependency Upgrades

Follow the **Context7 Protocol** for all third-party package upgrades:
1. **Inspect Target Version**: Check `apps/api/pyproject.toml` or `apps/web/package.json` for current bounds.
2. **Review Changelogs**: Identify breaking changes and deprecations in the target release.
3. **Minimal Diff**: Upgrade only the specific dependency required rather than doing wholesale `pip upgrade`.
4. **Validation Suite**:
   ```powershell
   # Run full test suites
   .\.venv\Scripts\python.exe -m pytest apps/api/tests -v
   ```

---

## 3. Database Schema Evolution & Alembic Migrations

To add or modify database tables:
1. **Model Definition**: Update SQLAlchemy 2.0 type-annotated models in `apps/api/app/models/`.
2. **Generate Migration**:
   ```powershell
   cd apps/api
   alembic revision --autogenerate -m "describe_schema_change"
   ```
3. **Inspect Migration File**:
   - Verify both `upgrade()` and `downgrade()` functions.
   - Enforce explicit column defaults, foreign key constraints, and indices.
   - **Never write destructive operations (`drop_table`, `drop_column`) against production without data migration plans.**
4. **Test Clean Migration From Zero**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest apps/api/tests/test_migrations.py
   ```

---

## 4. Gemini Model Upgrades

CodeGuard isolates LLM interactions within `app/agents/llm/`. To update or migrate model tiers:
1. **Configuration**: Edit `app/core/config.py` (`GEMINI_MODEL_FAST`, `GEMINI_MODEL_REASONING`).
2. **Verify Provider Abstraction**:
   - Check structured output schemas conforming to `ReviewFinding`.
   - Ensure token cost formula in `app/agents/llm/gemini.py` matches current pricing.
3. **Empirical Validation**: Run full test suite to verify that structured output schemas and model responses remain consistent.
   ```powershell
   .\.venv\Scripts\python.exe -m pytest apps/api/tests -k "llm or agent or review" -v
   ```

---

## 5. Tree-sitter Parser Updates

When upgrading Tree-sitter language grammars:
1. Test grammar loading in `packages/code-intelligence/code_intelligence/treesitter/`.
2. Verify AST symbol extraction across functions, classes, decorators, and nested blocks.
3. Verify syntax-broken sources degrade gracefully to line diffs without throwing unhandled exceptions.

---

## 7. Operational Health Probes

Verify active service health locally or in staging:
- **Liveness Probe**: `GET http://localhost:8000/api/v1/live` -> HTTP 200 `{"status": "alive"}`
- **Readiness Probe**: `GET http://localhost:8000/api/v1/health` -> HTTP 200 `{"status": "healthy", "database": "connected", "redis": "connected"}`
- **Frontend Dashboard**: `GET http://localhost:3000/` -> HTTP 200 (Next.js SSR)
