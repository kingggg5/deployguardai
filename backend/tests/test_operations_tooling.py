from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text

# CI runs pytest from ``backend/``; expose the repository-level operations
# scripts without requiring the application package to install them.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backup_database import backup_sqlite
from scripts.retention_report import _table_report


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
