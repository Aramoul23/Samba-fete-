#!/usr/bin/env python3
"""Samba Fête — Automated database backup.

Usage:
    python scripts/backup_db.py              # Backup now
    python scripts/backup_db.py --schedule   # Run on schedule (cron helper)

Environment:
    DATABASE_URL    — PostgreSQL connection string
    BACKUP_DIR      — Directory for backups (default: ./backups)
    BACKUP_RETAIN   — Days to keep backups (default: 30)

For Railway/production, add to crontab:
    0 3 * * * cd /app && python scripts/backup_db.py >> /var/log/backup.log 2>&1
"""
import os
import sys
import gzip
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def backup_postgres(database_url, backup_dir, retain_days=30):
    """Backup PostgreSQL database using pg_dump."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"samba_fete_{timestamp}.sql.gz"
    filepath = backup_dir / filename

    print(f"[{datetime.now()}] Starting backup to {filepath}")

    # Run pg_dump
    try:
        proc = subprocess.run(
            ["pg_dump", "--no-owner", "--no-acl", "-d", database_url],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            print(f"ERROR: pg_dump failed: {proc.stderr}", file=sys.stderr)
            return False

        # Compress and save
        with gzip.open(filepath, "wt", encoding="utf-8") as f:
            f.write(proc.stdout)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"[{datetime.now()}] Backup complete: {filename} ({size_mb:.1f} MB)")

    except FileNotFoundError:
        print("ERROR: pg_dump not found. Install postgresql-client.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("ERROR: pg_dump timed out after 300s", file=sys.stderr)
        return False

    # Clean old backups
    cleanup_old_backups(backup_dir, retain_days)
    return True


def backup_sqlite(db_path, backup_dir, retain_days=30):
    """Backup SQLite database file."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"samba_fete_{timestamp}.db.gz"
    filepath = backup_dir / filename

    print(f"[{datetime.now()}] Starting SQLite backup to {filepath}")

    with open(db_path, "rb") as f_in:
        with gzip.open(filepath, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    size_mb = filepath.stat().st_size / (1024 * 1024)
    print(f"[{datetime.now()}] Backup complete: {filename} ({size_mb:.1f} MB)")

    cleanup_old_backups(backup_dir, retain_days)
    return True


def cleanup_old_backups(backup_dir, retain_days):
    """Remove backups older than retain_days."""
    cutoff = datetime.now() - timedelta(days=retain_days)
    removed = 0
    for f in backup_dir.glob("samba_fete_*.gz"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            removed += 1
    if removed:
        print(f"[{datetime.now()}] Cleaned up {removed} old backups")


def main():
    database_url = os.environ.get("DATABASE_URL", "")
    backup_dir = os.environ.get("BACKUP_DIR", "./backups")
    retain_days = int(os.environ.get("BACKUP_RETAIN", "30"))
    db_path = os.environ.get("SQLITE_DB_PATH", "./samba_fete.db")

    if database_url.startswith("postgresql://"):
        success = backup_postgres(database_url, backup_dir, retain_days)
    else:
        success = backup_sqlite(db_path, backup_dir, retain_days)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
