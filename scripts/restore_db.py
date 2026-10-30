#!/usr/bin/env python
"""
CodeGuard — Database Restore Utility
Restores database from a compressed backup archive with SHA-256 verification
and pre-flight safety gates.
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
from urllib.parse import urlparse


def compute_sha256(file_path: str) -> str:
    """Calculate SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_checksum(archive_path: str) -> bool:
    """Check archive SHA-256 against companion .json metadata if available."""
    meta_path = archive_path.replace(".gz", "").rsplit(".", 1)[0] + ".json"
    if not os.path.exists(meta_path):
        meta_path = archive_path.replace(".sqlite.gz", ".json").replace(".sql.gz", ".json")

    if os.path.exists(meta_path):
        try:
            with open(meta_path) as f:
                data = json.load(f)
            expected_sha = data.get("sha256")
            if expected_sha:
                actual_sha = compute_sha256(archive_path)
                if actual_sha != expected_sha:
                    print(f"Checksum mismatch! Expected {expected_sha}, got {actual_sha}", file=sys.stderr)
                    return False
                print(f"Checksum verified: {actual_sha}")
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Could not verify metadata file: {e}")
    return True


def decompress_archive(archive_path: str, output_path: str) -> None:
    """Decompress .gz archive to target file."""
    with gzip.open(archive_path, "rb") as f_in, open(output_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def restore_sqlite(decompressed_path: str, target_db_path: str) -> None:
    """Restore SQLite database."""
    target_dir = os.path.dirname(os.path.abspath(target_db_path))
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)
    shutil.copy2(decompressed_path, target_db_path)


def restore_postgres(db_url: str, decompressed_sql_path: str) -> None:
    """Restore PostgreSQL database from plain-text SQL dump."""
    parsed = urlparse(db_url)
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = parsed.password

    cmd = [
        "psql",
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-d", parsed.path.lstrip("/"),
        "-f", decompressed_sql_path,
    ]

    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        # Fall back to Docker container execution if local psql not present
        docker_cmd = [
            "docker", "exec", "-i", "codeguard-postgres",
            "psql", "-U", parsed.username or "codeguard",
            "-d", parsed.path.lstrip("/") or "codeguard",
        ]
        with open(decompressed_sql_path, "rb") as sql_in:
            subprocess.run(docker_cmd, stdin=sql_in, check=True)


def verify_restored_db(db_url: str) -> bool:
    """Verify that restored database can be queried."""
    try:
        if db_url.startswith("sqlite"):
            db_path = db_url.replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            print(f"Restored database verified. Found {len(tables)} tables: {tables[:5]}...")
            return True
        elif db_url.startswith("postgres"):
            from sqlalchemy import create_engine, text
            engine = create_engine(db_url)
            with engine.connect() as conn:
                res = conn.execute(text("SELECT 1")).scalar()
            return res == 1
    except (sqlite3.Error, OSError) as e:
        print(f"Post-restore verification failed: {e}", file=sys.stderr)
        return False
    except Exception as e:  # noqa: BLE001
        print(f"Post-restore verification failed: {e}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="CodeGuard Database Restore Utility")
    parser.add_argument("--backup-file", required=True, help="Path to the .gz backup archive")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///local_verify_restored.db"))
    parser.add_argument("--confirm-restore", action="store_true", help="Explicit confirmation to overwrite target database")
    args = parser.parse_args()

    if not args.confirm_restore:
        print("SAFETY ERROR: You must specify --confirm-restore to execute a database restoration.", file=sys.stderr)
        print("This operation will overwrite data in the target database!", file=sys.stderr)
        return 2

    if not os.path.exists(args.backup_file):
        print(f"Error: Backup archive '{args.backup_file}' does not exist.", file=sys.stderr)
        return 1

    print(f"Initiating restoration from: {args.backup_file}")
    if not verify_checksum(args.backup_file):
        print("Restoration aborted: Checksum verification failed.", file=sys.stderr)
        return 1

    temp_unpacked = args.backup_file.replace(".gz", ".tmp_restore")
    try:
        print("Decompressing backup archive...")
        decompress_archive(args.backup_file, temp_unpacked)

        db_url = args.database_url
        if db_url.startswith("sqlite"):
            db_path = db_url.replace("sqlite:///", "")
            restore_sqlite(temp_unpacked, db_path)
        elif db_url.startswith("postgres"):
            restore_postgres(db_url, temp_unpacked)
        else:
            print(f"Unsupported database scheme: {db_url}", file=sys.stderr)
            return 1

        print("Restoration written. Verifying integrity...")
        if not verify_restored_db(db_url):
            return 1

        print("Database restoration completed and verified successfully!")
        return 0

    finally:
        if os.path.exists(temp_unpacked):
            os.remove(temp_unpacked)


if __name__ == "__main__":
    sys.exit(main())
