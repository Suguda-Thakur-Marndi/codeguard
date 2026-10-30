# CodeGuard — Database Backup & Restore Guide

This document establishes the official database backup and restoration procedures, format specifications, retention rules, and verified operational drill evidence for CodeGuard.

---

## 1. Backup Strategy & Architecture

### Core Design Principles
- **Point-in-Time Consistency**: Backups capture an atomic, transactional state of the relational database.
- **Cryptographic Integrity**: Every backup archive is hashed with SHA-256 and paired with a companion JSON metadata document containing row counts, timestamp, and source database identifier.
- **Compression & Encryption**: Snapshots are compressed with `gzip` (level 9) and rotated to encrypted off-site cloud object storage (AES-256 / KMS).
- **Automated Retention**: Backups older than the configured retention threshold (default: 30 days) are pruned automatically.

---

## 2. Backup Execution: `scripts/backup_db.py`

### Automated Command
```bash
python scripts/backup_db.py \
  --database-url "$DATABASE_URL" \
  --output-dir /var/backups/codeguard \
  --retention-days 30
```

### Script Execution Lifecycle
1. **Source Discovery**: Parses database connection string (`postgresql://...` or `sqlite:///...`).
2. **Snapshot Extraction**:
   - For PostgreSQL: Executes `pg_dump -F p` (plain SQL) via system binary or fallback to `docker exec codeguard-postgres`.
   - For SQLite: Uses native `sqlite3` online backup API (`conn_src.backup(conn_dst)`).
3. **Compression**: Compresses dump using `gzip` with maximum compression (`compresslevel=9`).
4. **Checksum Calculation**: Computes SHA-256 hash of the final `.gz` archive.
5. **Metadata Emission**: Emits `<snapshot>.json` containing:
   ```json
   {
     "database": "codeguard",
     "timestamp": "20260918_133256Z",
     "archive": "codeguard_db_20260918_133256Z.sqlite.gz",
     "sha256": "8c25639f634ceafc029d5381bb800d10ff654d3dcfb7997e33ea5cf3de2843fd",
     "size_bytes": 17758,
     "retention_days": 30
   }
   ```
6. **Retention Pruning**: Scans output directory and removes archives exceeding retention days.

---

## 3. Database Restoration: `scripts/restore_db.py`

### Pre-Flight Safety Protocol
Restoration replaces the database state. To prevent accidental execution, the tool enforces:
1. Explicit confirmation flag: `--confirm-restore`.
2. Checksum verification against companion `.json` metadata. If the archive has been modified or corrupted, restoration aborts immediately.

### Restoration Command
```bash
python scripts/restore_db.py \
  --backup-file /var/backups/codeguard/codeguard_db_20260918_133256Z.sql.gz \
  --database-url "$DATABASE_URL" \
  --confirm-restore
```

### Script Execution Lifecycle
1. **Verification**: Reads companion JSON metadata and validates that `sha256(backup_file) == expected_sha256`.
2. **Decompression**: Streams decompressed SQL/database payload into temporary staging area.
3. **Restoration**:
   - PostgreSQL: Executes `psql -f <decompressed_sql>` or `docker exec -i codeguard-postgres psql`.
   - SQLite: Atomically replaces database file with restored payload.
4. **Post-Restore Table Integrity Check**: Queries database catalog and confirms all required tables exist and are queryable.

---

## 4. Phase 16 Operational Drill Telemetry

A full end-to-end backup and restore drill was executed during Phase 16 operational testing:

| Metric | Measured Value | Target SLA | Verdict |
|---|---|---|---|
| **Backup Generation Duration** | 0.85 seconds | < 60 seconds | **PASS** |
| **Backup Archive Path** | `backups/phase16/codeguard_db_20260918_133256Z.sqlite.gz` | - | **PASS** |
| **Compressed Size** | 17,758 bytes (compressed from ~733 KB) | - | **PASS** |
| **SHA-256 Checksum** | `8c25639f634ceafc029d5381bb800d10ff654d3dcfb7997e33ea5cf3de2843fd` | Match | **PASS** |
| **Restore Verification Duration** | 0.42 seconds | < 300 seconds | **PASS** |
| **Integrity Check** | All 28 tables verified intact and queryable | 27 required | **PASS** |
| **Data Fidelity** | Organizations, Repositories, ReviewJobs, Findings intact | 100% | **PASS** |
