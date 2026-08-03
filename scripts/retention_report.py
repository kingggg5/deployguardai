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
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, inspect, text
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
AUDIT_CONFIRMATION = "DELETE-EXPIRED-AUDIT-EVENTS"
RLS_PROTECTED_TARGETS = {"audit_events", "operational_events"}


def _legal_hold_state(
    path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read an operator-managed global hold file and honor optional expiry."""

    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Legal-hold control file does not exist: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("active"), bool):
        raise ValueError("Legal-hold file must contain an active boolean")
    expires_at = payload.get("expires_at")
    expired = False
    if expires_at:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise ValueError("Legal-hold expires_at must include a timezone")
        expired = expiry <= (now or datetime.now(UTC))
    return {
        "active": bool(payload["active"]) and not expired,
        "reason": str(payload.get("reason") or "").strip(),
        "expires_at": expires_at,
        "expired": expired,
        "path": str(resolved),
    }


def _append_deletion_audit(path: Path, payload: dict[str, Any]) -> None:
    """Append and fsync one JSONL audit event before/after destructive work."""

    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    line = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        resolved,
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
        0o600,
    )
    try:
        os.write(descriptor, line)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _database_url(value: str | None) -> str:
    database_url = (
        value
        or os.getenv("RETENTION_DATABASE_URL", "")
        or os.getenv("DATABASE_URL", "")
    ).strip()
    if not database_url:
        raise ValueError(
            "RETENTION_DATABASE_URL, DATABASE_URL, or --database-url is required"
        )
    return database_url


def _assert_retention_access(engine: Engine, tables: list[str]) -> None:
    """Refuse misleading cross-tenant reports under an RLS runtime role."""

    if engine.dialect.name != "postgresql":
        return
    protected = sorted(set(tables) & RLS_PROTECTED_TARGETS)
    if not protected:
        return
    with engine.connect() as connection:
        active = {
            table: bool(
                connection.scalar(
                    text("SELECT row_security_active(to_regclass(:table))"),
                    {"table": table},
                )
            )
            for table in protected
        }
    blocked = [table for table, enabled in active.items() if enabled]
    if blocked:
        raise ValueError(
            "Retention would be filtered by tenant RLS for: "
            + ", ".join(blocked)
            + ". Use a short-lived audited RETENTION_DATABASE_URL."
        )


def _quoted_identifier(engine: Engine, value: str) -> str:
    return engine.dialect.identifier_preparer.quote(value)


def _table_report(
    engine: Engine,
    table: str,
    timestamp_column: str,
    cutoff: datetime,
    *,
    apply: bool,
    batch_size: int = 1_000,
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
    if apply and "id" not in columns:
        return {
            "table": table,
            "timestamp_column": timestamp_column,
            "state": "missing_primary_key",
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
            quoted_id = _quoted_identifier(engine, "id")
            select_ids = text(
                f"SELECT {quoted_id} FROM {quoted_table} "
                f"WHERE {quoted_column} < :cutoff "
                f"ORDER BY {quoted_column}, {quoted_id} LIMIT :batch_size"
            )
            delete_ids = text(
                f"DELETE FROM {quoted_table} WHERE {quoted_id} IN :row_ids"
            ).bindparams(bindparam("row_ids", expanding=True))
            while deleted_rows < candidate_rows:
                row_ids = list(
                    connection.execute(
                        select_ids,
                        {
                            "cutoff": cutoff,
                            "batch_size": min(
                                batch_size,
                                candidate_rows - deleted_rows,
                            ),
                        },
                    ).scalars()
                )
                if not row_ids:
                    break
                deleted_rows += int(
                    connection.execute(
                        delete_ids,
                        {"row_ids": row_ids},
                    ).rowcount
                    or 0
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
        help=(
            "Database URL (defaults to RETENTION_DATABASE_URL, then DATABASE_URL "
            "for local SQLite)"
        ),
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
    parser.add_argument(
        "--confirm-audit",
        help=(
            "Additional acknowledgement required when deleting audit_events: "
            f"{AUDIT_CONFIRMATION}"
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1_000,
        help="Maximum rows deleted per transaction (default: 1000)",
    )
    parser.add_argument(
        "--legal-hold-file",
        type=Path,
        default=os.getenv("RETENTION_LEGAL_HOLD_FILE"),
        help="Required operator-managed JSON control file for --apply",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=os.getenv("RETENTION_AUDIT_LOG"),
        help="Required append-only JSONL deletion audit destination for --apply",
    )
    parser.add_argument(
        "--operator",
        default=os.getenv("RETENTION_OPERATOR", ""),
        help="Audited operator or scheduler identity required for --apply",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    engine: Engine | None = None
    audit_started = False
    audit_id = ""
    try:
        if args.days < 1:
            raise ValueError("--days must be at least 1")
        if not 1 <= args.batch_size <= 10_000:
            raise ValueError("--batch-size must be between 1 and 10000")
        if args.apply and args.confirm != CONFIRMATION:
            raise ValueError(
                f"--apply requires --confirm {CONFIRMATION}"
            )
        if args.apply and not args.table:
            raise ValueError("--apply requires at least one explicit --table")
        if (
            args.apply
            and "audit_events" in args.table
            and args.confirm_audit != AUDIT_CONFIRMATION
        ):
            raise ValueError(
                "Deleting audit_events requires --confirm-audit "
                f"{AUDIT_CONFIRMATION}"
            )
        legal_hold = None
        if args.legal_hold_file:
            legal_hold = _legal_hold_state(args.legal_hold_file)
        if args.apply:
            if legal_hold is None:
                raise ValueError("--apply requires --legal-hold-file")
            if legal_hold["active"]:
                raise ValueError(
                    "Retention apply is blocked by the active global legal hold"
                )
            if not args.audit_log:
                raise ValueError("--apply requires --audit-log")
            if not args.operator.strip():
                raise ValueError("--apply requires --operator")
        database_url = _database_url(args.database_url)
        if (
            database_url.startswith(("postgresql://", "postgresql+"))
            and not args.database_url
            and not os.getenv("RETENTION_DATABASE_URL")
        ):
            raise ValueError(
                "PostgreSQL retention requires --database-url or the dedicated "
                "RETENTION_DATABASE_URL maintenance credential"
            )
        engine = create_engine(database_url, pool_pre_ping=True)
        cutoff = datetime.now(UTC) - timedelta(days=args.days)
        tables = args.table or list(RETENTION_TARGETS)
        _assert_retention_access(engine, tables)
        audit_id = f"retention-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        if args.apply:
            _append_deletion_audit(
                args.audit_log,
                {
                    "event": "retention_started",
                    "audit_id": audit_id,
                    "operator": args.operator.strip(),
                    "cutoff": cutoff.isoformat(),
                    "tables": tables,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            audit_started = True
        results = [
            _table_report(
                engine,
                table,
                RETENTION_TARGETS[table],
                cutoff,
                apply=args.apply,
                batch_size=args.batch_size,
            )
            for table in tables
        ]
        if args.apply:
            _append_deletion_audit(
                args.audit_log,
                {
                    "event": "retention_completed",
                    "audit_id": audit_id,
                    "operator": args.operator.strip(),
                    "cutoff": cutoff.isoformat(),
                    "results": results,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        print(
            json.dumps(
                {
                    "dry_run": not args.apply,
                    "cutoff": cutoff.isoformat(),
                    "legal_hold": legal_hold,
                    "batch_size": args.batch_size,
                    "tables": results,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    except (json.JSONDecodeError, ValueError, OSError, SQLAlchemyError) as error:
        if audit_started and args.audit_log:
            try:
                _append_deletion_audit(
                    args.audit_log,
                    {
                        "event": "retention_failed",
                        "audit_id": audit_id,
                        "operator": args.operator.strip(),
                        "error_type": type(error).__name__,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            except OSError:
                # Preserve the original database/control error for the
                # scheduler; an unwritable audit target is already fatal.
                pass
        print(f"retention_failed: {error}")
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
