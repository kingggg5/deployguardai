import pytest
from sqlalchemy import select

from app.database import Database
from app.rls import TENANT_SESSION_INFO_KEY, set_tenant_context


def test_tenant_context_is_sqlite_safe_and_session_scoped(tmp_path) -> None:
    database = Database(
        f"sqlite:///{(tmp_path / 'rls-context.db').as_posix()}"
    )
    session = database.session_factory()
    try:
        set_tenant_context(
            session, "00000000-0000-0000-0000-000000000010"
        )
        assert session.info[TENANT_SESSION_INFO_KEY].endswith("0010")
        assert session.scalar(select(1)) == 1
        session.commit()
        assert session.scalar(select(1)) == 1
    finally:
        session.close()
        database.dispose()


def test_tenant_context_rejects_empty_or_oversized_ids(tmp_path) -> None:
    database = Database(
        f"sqlite:///{(tmp_path / 'rls-validation.db').as_posix()}"
    )
    session = database.session_factory()
    try:
        for invalid in ("", " ", "x" * 37):
            with pytest.raises(ValueError):
                set_tenant_context(session, invalid)
    finally:
        session.close()
        database.dispose()
