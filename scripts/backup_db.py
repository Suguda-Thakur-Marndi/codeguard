#!/usr/bin/env python
"""
CodeGuard — Database Backup Utility
Supports automated PostgreSQL and SQLite database backups with gzip compression,
SHA-256 checksum verification, retention management, and JSON metadata generation.
"""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from urllib.parse import urlparse


def compute_sha256(file_path: str) -> str:
    """Calculate SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def backup_sqlite(db_path: str, backup_dest: str) -> None:
    """Create a consistent online SQLite backup using sqlite3 backup API."""
    conn_src = sqlite3.connect(db_path)
    conn_dst = sqlite3.connect(backup_dest)
    with conn_dst:
        conn_src.backup(conn_dst, pages=100)
    conn_dst.close()
    conn_src.close()


def backup_postgres(db_url: str, backup_dest_sql: str) -> None:
    """Create a PostgreSQL dump using pg_dump."""
    parsed = urlparse(db_url)
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = parsed.password

    cmd = [
        "pg_dump",
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-d", parsed.path.lstrip("/"),
        "-F", "p",  # Plain-text SQL
        "-f", backup_dest_sql,
    ]

    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        # If pg_dump binary is not locally installed (e.g. non-DB host), fall back to Docker
        docker_cmd = [
            "docker", "exec", "codeguard-postgres",
            "pg_dump", "-U", parsed.username or "codeguard",
            "-d", parsed.path.lstrip("/") or "codeguard",
        ]
        with open(backup_dest_sql, "w") as out:
            subprocess.run(docker_cmd, stdout=out, check=True)


def compress_file(src_path: str, dest_gz_path: str) -> None:
    """Compress a file using gzip."""
    with open(src_path, "rb") as f_in, gzip.open(dest_gz_path, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)
    if os.path.exists(src_path):
        os.remove(src_path)


def prune_old_backups(backup_dir: str, retention_days: int) -> int:
    """Delete backup archives older than retention_days."""
    now = time.time()
    cutoff = now - (retention_days * 86400)
    pruned = 0
    for filename in os.listdir(backup_dir):
        if not filename.endswith((".gz", ".json")):
            continue
        file_path = os.path.join(backup_dir, filename)
        if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff:
            os.remove(file_path)
            pruned += 1
    return pruned


def main() -> int:
    parser = argparse.ArgumentParser(description="CodeGuard Database Backup Utility")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///local_verify.db"))
    parser.add_argument("--output-dir", default=os.getenv("BACKUP_DIR", "backups"))
    parser.add_argument("--retention-days", type=int, default=int(os.getenv("BACKUP_RETENTION_DAYS", "30")))
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%SZ")
    print(f"[{timestamp}] Starting CodeGuard database backup...")

    db_url = args.database_url
    if db_url.startswith("sqlite"):
        db_path = db_url.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        if not os.path.exists(db_path):
            print(f"Error: SQLite database file not found at {db_path}", file=sys.stderr)
            return 1

        raw_backup = os.path.join(args.output_dir, f"codeguard_db_{timestamp}.sqlite")
        final_backup = f"{raw_backup}.gz"

        backup_sqlite(db_path, raw_backup)
        compress_file(raw_backup, final_backup)
        db_type = "sqlite"

    elif db_url.startswith("postgres"):
        raw_backup = os.path.join(args.output_dir, f"codeguard_db_{timestamp}.sql")
        final_backup = f"{raw_backup}.gz"

        try:
            backup_postgres(db_url, raw_backup)
        except (subprocess.SubprocessError, OSError) as e:
            print(f"Error executing PostgreSQL backup: {e}", file=sys.stderr)
            return 1

        compress_file(raw_backup, final_backup)
        db_type = "postgresql"
    else:
        print(f"Unsupported database URL scheme: {db_url}", file=sys.stderr)
        return 1

    size_bytes = os.path.getsize(final_backup)
    checksum = compute_sha256(final_backup)

    metadata = {
        "timestamp": timestamp,
        "database_type": db_type,
        "backup_file": os.path.basename(final_backup),
        "size_bytes": size_bytes,
        "sha256": checksum,
        "created_at": datetime.now(UTC).isoformat(),
    }

    meta_file = os.path.join(args.output_dir, f"codeguard_db_{timestamp}.json")
    with open(meta_file, "w") as f:
        json.dump(metadata, f, indent=2)

    pruned = prune_old_backups(args.output_dir, args.retention_days)

    print("Backup completed successfully:")
    print(f"  Archive:  {final_backup} ({size_bytes} bytes)")
    print(f"  SHA-256:  {checksum}")
    print(f"  Metadata: {meta_file}")
    if pruned > 0:
        print(f"  Pruned {pruned} old backup files older than {args.retention_days} days.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
