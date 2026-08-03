from pathlib import Path

import pytest
from sqlalchemy import text

from app.database import Database


def test_database_head_check_accepts_migrated_database(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'ready.db').as_posix()}")
    try:
        database.migrate()
        database.require_migration_head()
    finally:
        database.dispose()


def test_database_head_check_rejects_unversioned_database(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'stale.db').as_posix()}")
    try:
        with database.engine.begin() as connection:
            connection.execute(text("CREATE TABLE example (id INTEGER)"))
        with pytest.raises(RuntimeError, match="not versioned"):
            database.require_migration_head()
    finally:
        database.dispose()


def test_runtime_security_check_rejects_non_postgresql_database(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'runtime.db').as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            database.require_postgresql_runtime_security()
    finally:
        database.dispose()
