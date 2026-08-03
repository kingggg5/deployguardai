import sqlite3
from pathlib import Path

import pytest

from scripts.restore_check import verify_sqlite


def test_restore_check_validates_sqlite_integrity_and_head(tmp_path: Path) -> None:
    backup = tmp_path / "verified.db"
    connection = sqlite3.connect(backup)
    try:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        connection.execute("INSERT INTO alembic_version VALUES ('0007')")
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    result = verify_sqlite(backup, expected_head="0007")

    assert result["integrity"] == "ok"
    assert result["alembic_head"] == "0007"
    assert result["table_count"] == 2

    with pytest.raises(RuntimeError, match="expected"):
        verify_sqlite(backup, expected_head="0008")
