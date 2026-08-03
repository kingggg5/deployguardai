from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        connect_args = (
            {"check_same_thread": False}
            if database_url.startswith("sqlite")
            else {}
        )
        self.engine: Engine = create_engine(
            database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )

    def create_schema(self) -> None:
        # Keep the development/test helper in sync with the Alembic metadata.
        # Model modules are imported lazily here to avoid a Base/model import
        # cycle during application startup.
        from . import (  # noqa: F401
            deployment_models,
            job_models,
            models,
            operations_models,
            provider_models,
        )

        Base.metadata.create_all(self.engine)

    def migrate(self, *, allow_legacy_bootstrap: bool = False) -> None:
        from . import (  # noqa: F401
            deployment_models,
            job_models,
            models,
            operations_models,
            provider_models,
        )

        existing_tables = set(inspect(self.engine).get_table_names())
        versioned = "alembic_version" in existing_tables
        if existing_tables and not versioned:
            if not allow_legacy_bootstrap:
                raise RuntimeError(
                    "Refusing to migrate an unversioned non-empty database. "
                    "Back it up and run the documented legacy bootstrap first."
                )
            known_tables = set(Base.metadata.tables)
            unexpected = existing_tables - known_tables
            if unexpected:
                raise RuntimeError(
                    "Legacy database contains unexpected tables: "
                    + ", ".join(sorted(unexpected))
                )
            required_legacy_tables = {
                "scenarios",
                "changes",
                "incidents",
                "incident_feedback",
            }
            missing = required_legacy_tables - existing_tables
            if missing:
                raise RuntimeError(
                    "Legacy database is missing required tables: "
                    + ", ".join(sorted(missing))
                )
            access_table_names = {
                "users",
                "access_tokens",
                "workspaces",
                "workspace_memberships",
                "repositories",
                "workspace_invitations",
                "audit_events",
            }
            Base.metadata.create_all(
                self.engine,
                tables=[
                    Base.metadata.tables[name]
                    for name in access_table_names
                ],
                checkfirst=True,
            )
            command.stamp(self._alembic_config(), "0001")
            command.upgrade(self._alembic_config(), "head")
            return
        command.upgrade(self._alembic_config(), "head")

    def _alembic_config(self) -> Config:
        backend_root = Path(__file__).resolve().parents[1]
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "migrations"))
        config.set_main_option(
            "sqlalchemy.url", self.database_url.replace("%", "%%")
        )
        return config

    def session(self) -> Generator[Session, None, None]:
        db_session = self.session_factory()
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()

    def dispose(self) -> None:
        self.engine.dispose()
