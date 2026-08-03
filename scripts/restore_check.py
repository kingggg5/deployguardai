"""Verify a database backup without mutating a target database.

SQLite backups are opened read-only and checked with ``PRAGMA integrity_check``.
PostgreSQL custom archives are inspected with ``pg_restore --list``. This is a
validation step, not a restore operation: production recovery still requires a
separate isolated target, credentials, approval, and a recorded RPO/RTO drill.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


def verify_sqlite(backup: Path, *, expected_head: str | None = None) -> dict[str, Any]:
    backup = backup.resolve()
    if not backup.exists():
        raise FileNotFoundError(f"SQLite backup does not exist: {backup}")
    connection = sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True)
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    try:
        version_row = connection.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
        version = version_row[0] if version_row else None
        table_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    if integrity != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    if expected_head and version != expected_head:
        raise RuntimeError(
            f"SQLite schema head is {version!r}; expected {expected_head!r}"
        )
    return {
        "format": "sqlite",
        "path": str(backup),
        "integrity": integrity,
        "alembic_head": version,
        "table_count": table_count,
    }


def verify_postgres_archive(backup: Path) -> dict[str, Any]:
    backup = backup.resolve()
    if not backup.exists():
        raise FileNotFoundError(f"PostgreSQL backup does not exist: {backup}")
    result = subprocess.run(
        ["pg_restore", "--list", str(backup)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "pg_restore could not inspect the archive; verify PostgreSQL client installation"
        )
    entries = [line for line in result.stdout.splitlines() if line.strip()]
    return {
        "format": "postgresql-custom",
        "path": str(backup),
        "entry_count": len(entries),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument(
        "--format",
        choices=("auto", "sqlite", "postgresql-custom"),
        default="auto",
    )
    parser.add_argument(
        "--expected-head",
        help="Optional Alembic revision required for a SQLite backup",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        backup_format = args.format
        if backup_format == "auto":
            backup_format = "sqlite" if args.backup.suffix.lower() in {".db", ".sqlite", ".sqlite3"} else "postgresql-custom"
        result = (
            verify_sqlite(args.backup, expected_head=args.expected_head)
            if backup_format == "sqlite"
            else verify_postgres_archive(args.backup)
        )
        print(json.dumps({"valid": True, **result}, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"restore_check_failed: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
