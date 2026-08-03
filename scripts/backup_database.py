"""Create a recoverable SQLite or PostgreSQL database backup.

SQLite backups use the online backup API and are written atomically through a
temporary file in the destination directory. PostgreSQL backups use the
installed ``pg_dump`` binary and the custom archive format. No overwrite is
allowed unless ``--force`` is passed explicitly.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError


def _database_url(value: str | None) -> str:
    database_url = (
        value
        or os.getenv("BACKUP_DATABASE_URL", "")
        or os.getenv("DATABASE_URL", "")
    ).strip()
    if not database_url:
        raise ValueError(
            "BACKUP_DATABASE_URL, DATABASE_URL, or --database-url is required"
        )
    return database_url


def _sqlite_path(database_url: str) -> Path | None:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite":
        return None
    database = parsed.database
    if not database or database == ":memory:":
        raise ValueError("An on-disk SQLite database is required for backup")
    path = Path(database)
    return path.resolve() if not path.is_absolute() else path


def _temporary_path(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(handle)
    temporary = Path(name)
    temporary.unlink(missing_ok=True)
    return temporary


def _assert_destination(destination: Path, *, force: bool) -> None:
    if destination.exists() and not force:
        raise FileExistsError(
            f"Backup destination exists: {destination}. Pass --force to replace it."
        )


def backup_sqlite(source: Path, destination: Path, *, force: bool) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Backup destination must differ from the source database")
    if not source.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")
    _assert_destination(destination, force=force)
    temporary = _temporary_path(destination)
    try:
        source_connection = sqlite3.connect(source)
        destination_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
        finally:
            destination_connection.close()
            source_connection.close()
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def backup_postgres(database_url: str, destination: Path, *, force: bool) -> None:
    _assert_destination(destination, force=force)
    temporary = _temporary_path(destination)
    parsed = make_url(database_url)
    if not parsed.database:
        raise ValueError("PostgreSQL database name is required for backup")
    connection_url = URL.create(
        drivername="postgresql",
        username=parsed.username,
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
        query=parsed.query,
    ).render_as_string(hide_password=False)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(temporary),
        "--dbname",
        connection_url,
    ]
    environment = os.environ.copy()
    if parsed.password:
        # Keep the password out of the process command line. pg_dump reads
        # PGPASSWORD for this one subprocess; production should prefer a
        # .pgpass file or managed identity where available.
        environment["PGPASSWORD"] = parsed.password
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "pg_dump failed; verify PostgreSQL client installation and credentials"
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help=(
            "Database URL (defaults to BACKUP_DATABASE_URL, then DATABASE_URL "
            "for local SQLite)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Backup archive path; existing files require --force",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Explicitly replace an existing backup archive",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        database_url = _database_url(args.database_url)
        destination = args.output.resolve()
        sqlite_source = _sqlite_path(database_url)
        if sqlite_source is not None:
            backup_sqlite(sqlite_source, destination, force=args.force)
            archive_format = "sqlite"
        else:
            if make_url(database_url).get_backend_name() != "postgresql":
                raise ValueError("Only SQLite and PostgreSQL URLs are supported")
            if not args.database_url and not os.getenv("BACKUP_DATABASE_URL"):
                raise ValueError(
                    "PostgreSQL backup requires --database-url or the dedicated "
                    "BACKUP_DATABASE_URL maintenance credential"
                )
            backup_postgres(database_url, destination, force=args.force)
            archive_format = "postgresql-custom"
        print(
            f"backup_created format={archive_format} path={destination} "
            f"bytes={destination.stat().st_size}"
        )
        return 0
    except (OSError, ValueError, RuntimeError, SQLAlchemyError) as error:
        print(f"backup_failed: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
