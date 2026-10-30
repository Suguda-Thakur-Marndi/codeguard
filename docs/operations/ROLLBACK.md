# CodeGuard — Rollback Procedures & Migration Constraints

This document establishes the official rollback procedures for application releases and documents database schema rollback compatibility and limitations.

---

## 1. Application Container Rollback Procedure

CodeGuard uses immutable, semantic-versioned container images in production. When a newly deployed version (e.g. `v1.1.0`) exhibits unexpected defects, operators execute a rollback to the prior known-good version (`v1.0.0`).

### Step-by-Step Container Rollback
1. **Identify Target Rollback Version**:
   Determine the prior stable git release tag and image tag (e.g., `v1.0.0-release`).

2. **Update Image Tags**:
   Update `APP_VERSION` and container image references in `.env.production` or Docker Compose:
   ```bash
   sed -i 's/APP_VERSION=.*/APP_VERSION=1.0.0/' .env.production
   sed -i 's/GIT_REVISION=.*/GIT_REVISION=v1.0.0-release/' .env.production
   ```

3. **Deploy Previous Application Version**:
   Restart the application containers using the target release:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --no-deps api worker web
   ```

4. **Verify Health Probes**:
   ```bash
   curl -sSf http://localhost:8000/api/v1/health | grep '"version":"1.0.0"'
   curl -sSf http://localhost:8000/api/v1/live
   curl -sSf http://localhost:8000/api/v1/ready
   ```

5. **Verify Webhook Ingestion**:
   Send a test ping webhook and verify HTTP 200/202 response.

---

## 2. Database Schema Rollback Compatibility & Limitations

> [!WARNING]
> **Database Rollback Invariant**:
> Application code can be rolled back in seconds, but database schema changes may not be safely reversible if data has already been written to new columns or modified by destructive operations.

### Migration Classification & Rollback Safety

| Migration Type | Examples | Rollback Safety | Procedure |
|---|---|---|---|
| **Additive (Non-Breaking)** | Adding a new table, adding a nullable column, adding an index. | **SAFE** | Application rollback does NOT require database downgrade. The previous application version simply ignores the new columns/tables. |
| **Index / Constraint Addition** | Adding a non-conflicting B-Tree index or foreign key. | **SAFE** | Previous code operates without modification. |
| **Destructive / Column Removal** | Dropping a column, renaming a column, altering column type. | **UNSAFE WITHOUT MANUAL MIGRATION** | Cannot rollback application without running an Alembic downgrade script. May result in data loss for data written while the new version was active. |

### Alembic Downgrade Procedure (Additive Migrations)
To revert a specific migration revision if required:
```bash
# Inspect current and prior revisions
docker compose -f docker-compose.prod.yml run --rm api alembic history
docker compose -f docker-compose.prod.yml run --rm api alembic current

# Downgrade by 1 revision
docker compose -f docker-compose.prod.yml run --rm api alembic downgrade -1
```

---

## 3. Zero-Downtime Deployment & the Expand-and-Contract Rule

To maintain zero/low downtime without rollback hazards, all CodeGuard schema changes MUST adhere to the **Expand-and-Contract Pattern**:

1. **Expand Phase (Release N)**:
   - Add new columns as `NULLABLE` or with safe defaults.
   - Do NOT drop or rename old columns.
   - Deploy database migration.
   - Deploy code that writes to both old and new columns, reading from old.

2. **Transition Phase (Release N+1)**:
   - Deploy code that reads from new columns.
   - Backfill historical data in the background.

3. **Contract Phase (Release N+2)**:
   - Once all traffic is migrated and stable for at least one full release cycle, drop the deprecated column in a separate cleanup migration.
