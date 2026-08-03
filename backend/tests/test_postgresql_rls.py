from contextlib import contextmanager
import os

from alembic import command
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database import Database
from app.rls import (
    DIRECT_TENANT_TABLES,
    INDIRECT_TENANT_TABLES,
    set_tenant_context,
)


APPLICATION_ROLE = "deployguard_rls_test_application"
APPLICATION_PASSWORD = "deployguard-rls-test-only"
POLICY_NAME = "deployguard_workspace_isolation"
WORKSPACE_A = "00000000-0000-0000-0000-000000000010"
WORKSPACE_B = "00000000-0000-0000-0000-000000000020"
USER_ID = "00000000-0000-0000-0000-000000000030"


def _drop_application_role(database: Database) -> None:
    with database.engine.begin() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
            {"role": APPLICATION_ROLE},
        )
        if exists:
            connection.exec_driver_sql(
                f'DROP OWNED BY "{APPLICATION_ROLE}"'
            )
            connection.exec_driver_sql(f'DROP ROLE "{APPLICATION_ROLE}"')


def _create_application_role(database: Database) -> None:
    _drop_application_role(database)
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            f'CREATE ROLE "{APPLICATION_ROLE}" LOGIN PASSWORD '
            f"'{APPLICATION_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOBYPASSRLS"
        )
        connection.exec_driver_sql(
            f'GRANT "{APPLICATION_ROLE}" TO CURRENT_USER'
        )
        connection.exec_driver_sql(
            f'GRANT USAGE ON SCHEMA public TO "{APPLICATION_ROLE}"'
        )
        protected = DIRECT_TENANT_TABLES + INDIRECT_TENANT_TABLES
        quoted_tables = ", ".join(f'"{item}"' for item in protected)
        connection.exec_driver_sql(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            f'{quoted_tables} TO "{APPLICATION_ROLE}"'
        )
        connection.exec_driver_sql(
            f'GRANT SELECT ON TABLE alembic_version TO "{APPLICATION_ROLE}"'
        )


def _seed_two_tenants(database: Database) -> None:
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, display_name, auth_provider, "
                "provider_subject, is_active, created_at) VALUES "
                "(:user_id, 'rls@example.com', 'RLS test', 'test', "
                "'rls:test', true, CURRENT_TIMESTAMP)"
            ),
            {"user_id": USER_ID},
        )
        for suffix, workspace_id in (("a", WORKSPACE_A), ("b", WORKSPACE_B)):
            repository_id = f"00000000-0000-0000-0000-0000000001{suffix}"
            scenario_id = f"rls-scenario-{suffix}"
            incident_id = f"rls-incident-{suffix}"
            connection.execute(
                text(
                    "INSERT INTO workspaces (id, name, slug, created_by_user_id, "
                    "created_at, updated_at) VALUES (:id, :name, :slug, :user_id, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": workspace_id,
                    "name": f"Tenant {suffix.upper()}",
                    "slug": f"rls-tenant-{suffix}",
                    "user_id": USER_ID,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO repositories (id, workspace_id, provider, "
                    "provider_repository_id, full_name, default_branch, visibility, "
                    "connection_state, data_mode, selected, created_at) VALUES "
                    "(:id, :workspace_id, 'test', :provider_id, :full_name, "
                    "'main', 'private', 'connected', 'connected', true, "
                    "CURRENT_TIMESTAMP)"
                ),
                {
                    "id": repository_id,
                    "workspace_id": workspace_id,
                    "provider_id": f"provider-{suffix}",
                    "full_name": f"rls/tenant-{suffix}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO scenarios (id, workspace_id, repository_id, "
                    "name, description, data_mode, is_active, sort_order, "
                    "service_graph) VALUES (:id, :workspace_id, :repository_id, "
                    ":name, 'RLS regression fixture', 'connected', false, 0, "
                    "CAST('{}' AS JSON))"
                ),
                {
                    "id": scenario_id,
                    "workspace_id": workspace_id,
                    "repository_id": repository_id,
                    "name": f"Scenario {suffix.upper()}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO incidents (id, workspace_id, repository_id, "
                    "scenario_id, data_mode, title, severity, status, started_at, "
                    "affected_services, summary, timeline, evidence, hypotheses) "
                    "VALUES (:id, :workspace_id, :repository_id, :scenario_id, "
                    "'connected', :title, 'sev3', 'investigating', CURRENT_TIMESTAMP, "
                    "CAST('[]' AS JSON), 'RLS regression fixture', "
                    "CAST('[]' AS JSON), CAST('[]' AS JSON), CAST('[]' AS JSON))"
                ),
                {
                    "id": incident_id,
                    "workspace_id": workspace_id,
                    "repository_id": repository_id,
                    "scenario_id": scenario_id,
                    "title": f"Incident {suffix.upper()}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO incident_feedback (id, incident_id, hypothesis_id, "
                    "verdict, note, submitted_at) VALUES (:id, :incident_id, "
                    "'hypothesis-1', 'confirmed', 'RLS regression fixture', "
                    "CURRENT_TIMESTAMP)"
                ),
                {"id": 10 if suffix == "a" else 20, "incident_id": incident_id},
            )
            connection.execute(
                text(
                    "INSERT INTO audit_events (id, workspace_id, actor_user_id, "
                    "action, resource_type, resource_id, request_id, event_metadata, "
                    "created_at) VALUES (:id, :workspace_id, :user_id, 'rls.test', "
                    "'test', :resource_id, :request_id, CAST('{}' AS JSON), "
                    "CURRENT_TIMESTAMP)"
                ),
                {
                    "id": f"00000000-0000-0000-0000-0000000000{suffix}",
                    "workspace_id": workspace_id,
                    "user_id": USER_ID,
                    "resource_id": f"resource-{suffix}",
                    "request_id": f"request-{suffix}",
                },
            )


@contextmanager
def _application_session(database: Database):
    connection = database.engine.connect()
    connection.exec_driver_sql(f'SET ROLE "{APPLICATION_ROLE}"')
    connection.commit()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        connection.exec_driver_sql("RESET ROLE")
        connection.commit()
        connection.close()


def _audit_count(session: Session) -> int:
    return int(
        session.scalar(text("SELECT COUNT(*) FROM audit_events")) or 0
    )


@pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DATABASE_URL"),
    reason="POSTGRES_TEST_DATABASE_URL is not configured",
)
def test_postgresql_rls_fails_closed_and_blocks_cross_tenant_crud() -> None:
    database = Database(os.environ["POSTGRES_TEST_DATABASE_URL"])
    config = database._alembic_config()
    try:
        if "alembic_version" in inspect(database.engine).get_table_names():
            command.downgrade(config, "base")
        command.upgrade(config, "head")
        _seed_two_tenants(database)
        _create_application_role(database)

        application_url = make_url(
            os.environ["POSTGRES_TEST_DATABASE_URL"]
        ).set(
            username=APPLICATION_ROLE,
            password=APPLICATION_PASSWORD,
        ).render_as_string(hide_password=False)
        application_database = Database(application_url)
        try:
            application_database.require_migration_head()
            application_database.require_postgresql_runtime_security()
        finally:
            application_database.dispose()
        with pytest.raises(RuntimeError, match="unsafe|RLS policy"):
            database.require_postgresql_runtime_security()

        with database.engine.connect() as connection:
            policies = set(
                connection.scalars(
                    text(
                        "SELECT tablename FROM pg_policies "
                        "WHERE schemaname = current_schema() "
                        "AND policyname = :policy"
                    ),
                    {"policy": POLICY_NAME},
                )
            )
            assert policies == set(
                DIRECT_TENANT_TABLES + INDIRECT_TENANT_TABLES
            )

        # No context is fail-closed for every operation.
        with _application_session(database) as session:
            assert _audit_count(session) == 0
            assert session.execute(
                text("UPDATE audit_events SET action = 'blocked'"),
            ).rowcount == 0
            assert session.execute(text("DELETE FROM audit_events")).rowcount == 0
            with pytest.raises(DBAPIError):
                session.execute(
                    text(
                        "INSERT INTO audit_events (id, workspace_id, actor_user_id, "
                        "action, resource_type, resource_id, request_id, "
                        "event_metadata, created_at) VALUES "
                        "('00000000-0000-0000-0000-000000000099', :workspace_id, "
                        ":user_id, 'blocked', 'test', 'blocked', 'blocked', "
                        "CAST('{}' AS JSON), CURRENT_TIMESTAMP)"
                    ),
                    {"workspace_id": WORKSPACE_A, "user_id": USER_ID},
                )
                session.commit()

        with _application_session(database) as session:
            set_tenant_context(session, WORKSPACE_A)
            assert _audit_count(session) == 1
            # Context is transaction-local in PostgreSQL but the Session hook
            # restores it after a commit starts the next transaction.
            session.commit()
            assert _audit_count(session) == 1
            assert session.scalar(
                text(
                    "SELECT COUNT(*) FROM incident_feedback"
                )
            ) == 1

            # Targeting another tenant is indistinguishable from no row.
            assert session.execute(
                text(
                    "UPDATE audit_events SET action = 'blocked' "
                    "WHERE workspace_id = :workspace_id"
                ),
                {"workspace_id": WORKSPACE_B},
            ).rowcount == 0
            assert session.execute(
                text(
                    "DELETE FROM audit_events WHERE workspace_id = :workspace_id"
                ),
                {"workspace_id": WORKSPACE_B},
            ).rowcount == 0

            # WITH CHECK rejects both cross-tenant inserts and moving a visible
            # row into another workspace.
            with pytest.raises(DBAPIError):
                session.execute(
                    text(
                        "INSERT INTO audit_events (id, workspace_id, actor_user_id, "
                        "action, resource_type, resource_id, request_id, "
                        "event_metadata, created_at) VALUES "
                        "('00000000-0000-0000-0000-000000000098', :workspace_id, "
                        ":user_id, 'blocked', 'test', 'blocked', 'blocked', "
                        "CAST('{}' AS JSON), CURRENT_TIMESTAMP)"
                    ),
                    {"workspace_id": WORKSPACE_B, "user_id": USER_ID},
                )
                session.commit()
            session.rollback()

            with pytest.raises(DBAPIError):
                session.execute(
                    text(
                        "UPDATE audit_events SET workspace_id = :workspace_id "
                        "WHERE workspace_id = :visible_workspace_id"
                    ),
                    {
                        "workspace_id": WORKSPACE_B,
                        "visible_workspace_id": WORKSPACE_A,
                    },
                )
                session.commit()
            session.rollback()

            # The indirect feedback policy follows the incident's tenant and
            # blocks reassignment to another tenant's incident.
            with pytest.raises(DBAPIError):
                session.execute(
                    text(
                        "UPDATE incident_feedback SET incident_id = "
                        "'rls-incident-b' WHERE id = 10"
                    )
                )
                session.commit()
            session.rollback()
            assert session.execute(
                text("DELETE FROM incident_feedback WHERE id = 20")
            ).rowcount == 0

        # Returning a connection to the pool must not carry the previous
        # workspace into a fresh application session.
        with _application_session(database) as session:
            assert _audit_count(session) == 0
    finally:
        _drop_application_role(database)
        if "alembic_version" in inspect(database.engine).get_table_names():
            command.downgrade(config, "base")
        database.dispose()
