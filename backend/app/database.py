from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, bindparam, create_engine, inspect, text
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

    def require_migration_head(self) -> None:
        """Fail startup when the database was not migrated by release tooling."""

        expected = ScriptDirectory.from_config(
            self._alembic_config()
        ).get_current_head()
        with self.engine.connect() as connection:
            existing_tables = set(inspect(connection).get_table_names())
            if "alembic_version" not in existing_tables:
                raise RuntimeError(
                    "Database is not versioned; run the migration release job"
                )
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        if current != expected:
            raise RuntimeError(
                "Database migration is not at head "
                f"(current={current!r}, expected={expected!r})"
            )

    def require_postgresql_runtime_security(self) -> None:
        """Verify that the long-lived role cannot bypass tenant RLS."""

        from .rls import DIRECT_TENANT_TABLES, INDIRECT_TENANT_TABLES

        if self.engine.dialect.name != "postgresql":
            raise RuntimeError("Production runtime security requires PostgreSQL")
        protected = DIRECT_TENANT_TABLES + INDIRECT_TENANT_TABLES
        with self.engine.connect() as connection:
            role = connection.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).mappings().one()
            if any(bool(value) for value in role.values()):
                raise RuntimeError(
                    "Production database runtime role has unsafe attributes"
                )
            if connection.scalar(
                text(
                    "SELECT has_schema_privilege(current_user, "
                    "current_schema(), 'CREATE')"
                )
            ):
                raise RuntimeError(
                    "Production database runtime role can create schema objects"
                )
            rows = connection.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, owner.rolname AS owner, "
                    "pg_has_role(current_user, owner.rolname, 'MEMBER') "
                    "AS can_assume_owner, "
                    "EXISTS (SELECT 1 FROM pg_policies p "
                    "WHERE p.schemaname = current_schema() "
                    "AND p.tablename = c.relname "
                    "AND p.policyname = 'deployguard_workspace_isolation') "
                    "AS has_policy, "
                    "has_table_privilege(current_user, c.oid, 'SELECT') "
                    "AND has_table_privilege(current_user, c.oid, 'INSERT') "
                    "AND has_table_privilege(current_user, c.oid, 'UPDATE') "
                    "AND has_table_privilege(current_user, c.oid, 'DELETE') "
                    "AS has_runtime_dml, "
                    "has_table_privilege(current_user, c.oid, 'TRUNCATE') "
                    "AS can_truncate "
                    "FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "JOIN pg_roles owner ON owner.oid = c.relowner "
                    "WHERE n.nspname = current_schema() "
                    "AND c.relname IN :protected"
                ).bindparams(bindparam("protected", expanding=True)),
                {"protected": protected},
            ).mappings().all()
        if {str(row["relname"]) for row in rows} != set(protected):
            raise RuntimeError("Production RLS table set is incomplete")
        if any(
            not bool(row["relrowsecurity"])
            or bool(row["can_assume_owner"])
            or not bool(row["has_policy"])
            or not bool(row["has_runtime_dml"])
            or bool(row["can_truncate"])
            for row in rows
        ):
            raise RuntimeError(
                "Production database role or tenant RLS policy is unsafe"
            )

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
