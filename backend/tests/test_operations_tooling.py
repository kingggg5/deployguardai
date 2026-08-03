from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# CI runs pytest from ``backend/``; expose the repository-level operations
# scripts without requiring the application package to install them.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backup_database import backup_sqlite
import scripts.retention_report as retention_report
import scripts.backup_database as backup_database
from scripts.retention_report import (
    _append_deletion_audit,
    _legal_hold_state,
    _table_report,
)
from scripts.restore_rehearsal import _pg_restore_command, rehearse_sqlite


def test_sqlite_backup_is_recoverable_and_does_not_overwrite_by_default(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "backups" / "source.db"
    engine = create_engine(f"sqlite:///{source.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)"))
        connection.execute(text("INSERT INTO records(value) VALUES ('kept')"))
    engine.dispose()

    backup_sqlite(source, destination, force=False)
    assert destination.exists()
    restored = create_engine(f"sqlite:///{destination.as_posix()}")
    with restored.connect() as connection:
        assert connection.execute(text("SELECT value FROM records")).scalar() == "kept"
    restored.dispose()

    with pytest.raises(FileExistsError):
        backup_sqlite(source, destination, force=False)


def test_postgres_tools_preserve_ssl_dsn_without_password_on_command_line(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = (
        "postgresql+psycopg://backup-user:private-password@db.example:5432/"
        "deployguard?sslmode=verify-full&channel_binding=require"
    )
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        Path(command[command.index("--file") + 1]).write_bytes(b"archive")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(backup_database.subprocess, "run", fake_run)
    destination = tmp_path / "backup.dump"
    backup_database.backup_postgres(
        database_url, destination, force=False
    )

    command_text = " ".join(observed["command"])
    assert "private-password" not in command_text
    assert "sslmode=verify-full" in command_text
    assert "channel_binding=require" in command_text
    assert observed["environment"]["PGPASSWORD"] == "private-password"
    assert destination.read_bytes() == b"archive"

    restore_command, restore_environment = _pg_restore_command(
        database_url,
        "deployguard_restore_test",
        destination,
    )
    restore_text = " ".join(restore_command)
    assert "private-password" not in restore_text
    assert "sslmode=verify-full" in restore_text
    assert "channel_binding=require" in restore_text
    assert restore_environment["PGPASSWORD"] == "private-password"


def test_retention_legal_hold_and_append_only_audit(tmp_path: Path) -> None:
    hold = tmp_path / "legal-hold.json"
    hold.write_text(
        '{"active":true,"reason":"incident review","expires_at":null}',
        encoding="utf-8",
    )

    state = _legal_hold_state(hold)

    assert state["active"] is True
    assert state["reason"] == "incident review"
    audit = tmp_path / "audit" / "retention.jsonl"
    _append_deletion_audit(audit, {"event": "retention_started", "rows": 1})
    _append_deletion_audit(audit, {"event": "retention_completed", "rows": 1})
    entries = [json.loads(line) for line in audit.read_text().splitlines()]
    assert [item["event"] for item in entries] == [
        "retention_started",
        "retention_completed",
    ]


def test_retention_failure_is_appended_after_started_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hold = tmp_path / "legal-hold.json"
    hold.write_text('{"active":false}', encoding="utf-8")
    audit = tmp_path / "retention.jsonl"
    database = tmp_path / "retention-failure.db"

    def fail_report(*_args, **_kwargs):
        raise SQLAlchemyError("simulated database failure")

    monkeypatch.setattr(retention_report, "_table_report", fail_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retention_report.py",
            "--database-url",
            f"sqlite:///{database.as_posix()}",
            "--apply",
            "--confirm",
            retention_report.CONFIRMATION,
            "--legal-hold-file",
            str(hold),
            "--audit-log",
            str(audit),
            "--operator",
            "retention-scheduler",
            "--table",
            "notifications",
        ],
    )

    assert retention_report.main() == 2
    entries = [json.loads(line) for line in audit.read_text().splitlines()]
    assert [item["event"] for item in entries] == [
        "retention_started",
        "retention_failed",
    ]
    assert entries[0]["audit_id"] == entries[1]["audit_id"]

def test_retention_report_is_dry_run_until_explicit_apply(tmp_path: Path) -> None:
    database = tmp_path / "retention.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE audit_events ("
                "id INTEGER PRIMARY KEY, created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO audit_events(created_at) VALUES (:created_at)"),
            {"created_at": datetime.now(UTC) - timedelta(days=120)},
        )
        connection.execute(
            text("INSERT INTO audit_events(created_at) VALUES (:created_at)"),
            {"created_at": datetime.now(UTC) - timedelta(days=5)},
        )

    cutoff = datetime.now(UTC) - timedelta(days=90)
    dry_run = _table_report(
        engine,
        "audit_events",
        "created_at",
        cutoff,
        apply=False,
    )
    assert dry_run["candidate_rows"] == 1
    assert dry_run["deleted_rows"] == 0
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM audit_events")).scalar() == 2

    applied = _table_report(
        engine,
        "audit_events",
        "created_at",
        cutoff,
        apply=True,
    )
    assert applied["candidate_rows"] == 1
    assert applied["deleted_rows"] == 1
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM audit_events")).scalar() == 1
    engine.dispose()


def test_sqlite_restore_rehearsal_uses_disposable_writable_copy(
    tmp_path: Path,
) -> None:
    backup = tmp_path / "backup.db"
    connection = sqlite3.connect(backup)
    try:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT)")
        connection.execute("INSERT INTO alembic_version VALUES ('0009')")
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    result = rehearse_sqlite(backup, expected_head="0009")

    assert result["isolated_target"] is True
    assert result["write_probe"] is True
    assert result["integrity"] == "ok"
    original = sqlite3.connect(backup)
    try:
        assert original.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = '__restore_rehearsal'"
        ).fetchone()[0] == 0
    finally:
        original.close()
