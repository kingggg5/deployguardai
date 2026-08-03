"""Report (or explicitly apply) retention candidates for operational records.

The default is a read-only report. Deletion requires both ``--apply`` and the
exact ``--confirm DELETE-EXPIRED-ROWS`` acknowledgement. The script only
touches the allow-listed operational tables below; it never deletes users,
workspaces, incidents, or evidence without an explicit future code change.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


RETENTION_TARGETS: dict[str, str] = {
    "audit_events": "created_at",
    "operational_events": "occurred_at",
    "notifications": "created_at",
    "webhook_deliveries": "created_at",
    "invitation_deliveries": "attempted_at",
    "provider_authorization_states": "created_at",
}
CONFIRMATION = "DELETE-EXPIRED-ROWS"


def _database_url(value: str | None) -> str:
    database_url = (value or os.getenv("DATABASE_URL", "")).strip()
    if not database_url:
        raise ValueError("DATABASE_URL or --database-url is required")
    return database_url


def _quoted_identifier(engine: Engine, value: str) -> str:
    return engine.dialect.identifier_preparer.quote(value)


def _table_report(
    engine: Engine,
    table: str,
    timestamp_column: str,
    cutoff: datetime,
    *,
    apply: bool,
) -> dict[str, Any]:
    table_names = set(inspect(engine).get_table_names())
    if table not in table_names:
        return {
            "table": table,
            "timestamp_column": timestamp_column,
            "state": "missing",
            "candidate_rows": 0,
            "deleted_rows": 0,
        }

    columns = {item["name"] for item in inspect(engine).get_columns(table)}
    if timestamp_column not in columns:
        return {
            "table": table,
            "timestamp_column": timestamp_column,
            "state": "missing_column",
            "candidate_rows": 0,
            "deleted_rows": 0,
        }

    quoted_table = _quoted_identifier(engine, table)
    quoted_column = _quoted_identifier(engine, timestamp_column)
    query = text(
        f"SELECT COUNT(*) FROM {quoted_table} "
        f"WHERE {quoted_column} < :cutoff"
    )
    with engine.connect() as connection:
        candidate_rows = int(connection.execute(query, {"cutoff": cutoff}).scalar() or 0)
        deleted_rows = 0
        if apply and candidate_rows:
            delete_query = text(
                f"DELETE FROM {quoted_table} "
                f"WHERE {quoted_column} < :cutoff"
            )
            deleted_rows = int(
                connection.execute(delete_query, {"cutoff": cutoff}).rowcount or 0
            )
            connection.commit()
    return {
        "table": table,
        "timestamp_column": timestamp_column,
        "state": "processed",
        "candidate_rows": candidate_rows,
        "deleted_rows": deleted_rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="Database URL (defaults to DATABASE_URL)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Rows older than this many days are candidates (default: 90)",
    )
    parser.add_argument(
        "--table",
        action="append",
        choices=sorted(RETENTION_TARGETS),
        help="Restrict the report to an allow-listed table (repeatable)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete candidates (requires --confirm)",
    )
    parser.add_argument(
        "--confirm",
        help=f"Required acknowledgement for --apply: {CONFIRMATION}",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.days < 1:
            raise ValueError("--days must be at least 1")
        if args.apply and args.confirm != CONFIRMATION:
            raise ValueError(
                f"--apply requires --confirm {CONFIRMATION}"
            )
        database_url = _database_url(args.database_url)
        engine = create_engine(database_url, pool_pre_ping=True)
        cutoff = datetime.now(UTC) - timedelta(days=args.days)
        tables = args.table or list(RETENTION_TARGETS)
        results = [
            _table_report(
                engine,
                table,
                RETENTION_TARGETS[table],
                cutoff,
                apply=args.apply,
            )
            for table in tables
        ]
        print(
            json.dumps(
                {
                    "dry_run": not args.apply,
                    "cutoff": cutoff.isoformat(),
                    "tables": results,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        engine.dispose()
        return 0
    except (ValueError, OSError, SQLAlchemyError) as error:
        print(f"retention_failed: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
