"""Short-lived schema-owner migration entrypoint for release automation."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from .database import Database


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("MIGRATION_DATABASE_URL", ""),
        help=(
            "Schema-owner PostgreSQL URL. Prefer MIGRATION_DATABASE_URL from "
            "a short-lived secret injection."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = args.database_url.strip()
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL is required")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    database = Database(database_url)
    try:
        database.migrate(allow_legacy_bootstrap=False)
        database.require_migration_head()
    finally:
        database.dispose()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
