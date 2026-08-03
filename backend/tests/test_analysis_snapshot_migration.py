import os

from alembic import command
import pytest
from sqlalchemy import JSON, bindparam, inspect, text

from app.database import Database
from app.engines import LEGACY_ANALYSIS_VERSION
from app.models import LEGACY_REPOSITORY_ID, LEGACY_WORKSPACE_ID


VERSION_COLUMNS = {
    "analysis_schema_version",
    "engine_version",
    "scoring_policy_version",
    "graph_version",
}


def _insert_legacy_snapshots(database: Database) -> None:
    change_values = {
        "id": "legacy-change",
        "workspace_id": LEGACY_WORKSPACE_ID,
        "repository_id": LEGACY_REPOSITORY_ID,
        "scenario_id": "legacy-scenario",
        "data_mode": "connected",
        "title": "Legacy analyzed change",
        "repository": "acme/legacy",
        "author": "legacy-bot",
        "commit_sha": "abcdef123456",
        "branch": "main",
        "created_at": "2026-08-01 00:00:00",
        "deployment_status": "analyzed",
        "deployment_environment": "staging",
        "changed_services": ["legacy-api"],
        "files_changed": 1,
        "lines_added": 2,
        "lines_deleted": 1,
        "flags": [],
        "test_coverage": 0.9,
        "rollback_ready": True,
        "observability_score": 0.8,
        "previous_failures": 0,
        "risk": {"overall_score": 12},
        "blast_radius": {"nodes": [], "edges": []},
    }
    incident_values = {
        "id": "legacy-incident",
        "workspace_id": LEGACY_WORKSPACE_ID,
        "repository_id": LEGACY_REPOSITORY_ID,
        "scenario_id": "legacy-scenario",
        "data_mode": "connected",
        "title": "Legacy incident",
        "severity": "sev3",
        "status": "resolved",
        "started_at": "2026-08-01 00:01:00",
        "resolved_at": "2026-08-01 00:05:00",
        "affected_services": ["legacy-api"],
        "correlated_change_id": "legacy-change",
        "summary": "Legacy analysis without recorded engine versions.",
        "timeline": [],
        "evidence": [],
        "hypotheses": [],
    }
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO scenarios ("
                "id, workspace_id, repository_id, name, description, data_mode, "
                "is_active, sort_order, active_change_id, active_incident_id, "
                "service_graph"
                ") VALUES ("
                ":id, :workspace_id, :repository_id, :name, :description, "
                ":data_mode, :is_active, :sort_order, :active_change_id, "
                ":active_incident_id, :service_graph"
                ")"
            ).bindparams(bindparam("service_graph", type_=JSON)),
            {
                "id": "legacy-scenario",
                "workspace_id": LEGACY_WORKSPACE_ID,
                "repository_id": LEGACY_REPOSITORY_ID,
                "name": "Legacy scenario",
                "description": "Migration regression fixture",
                "data_mode": "connected",
                "is_active": False,
                "sort_order": 0,
                "active_change_id": None,
                "active_incident_id": None,
                "service_graph": {"nodes": [], "edges": []},
            },
        )
        connection.execute(
            text(
                "INSERT INTO changes ("
                + ", ".join(change_values)
                + ") VALUES ("
                + ", ".join(f":{key}" for key in change_values)
                + ")"
            ).bindparams(
                *(
                    bindparam(key, type_=JSON)
                    for key in (
                        "changed_services",
                        "flags",
                        "risk",
                        "blast_radius",
                    )
                )
            ),
            change_values,
        )
        connection.execute(
            text(
                "INSERT INTO incidents ("
                + ", ".join(incident_values)
                + ") VALUES ("
                + ", ".join(f":{key}" for key in incident_values)
                + ")"
            ).bindparams(
                *(
                    bindparam(key, type_=JSON)
                    for key in (
                        "affected_services",
                        "timeline",
                        "evidence",
                        "hypotheses",
                    )
                )
            ),
            incident_values,
        )


def _exercise_analysis_snapshot_migration(database: Database) -> None:
    config = database._alembic_config()
    command.upgrade(config, "0007")
    _insert_legacy_snapshots(database)

    command.upgrade(config, "0008")
    inspector = inspect(database.engine)
    assert VERSION_COLUMNS <= {
        column["name"] for column in inspector.get_columns("changes")
    }
    assert VERSION_COLUMNS <= {
        column["name"] for column in inspector.get_columns("incidents")
    }
    with database.engine.connect() as connection:
        for table_name in ("changes", "incidents"):
            row = connection.execute(
                text(
                    "SELECT "
                    + ", ".join(sorted(VERSION_COLUMNS))
                    + f" FROM {table_name}"
                )
            ).one()
            assert set(row) == {LEGACY_ANALYSIS_VERSION}
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO changes ("
                "id, workspace_id, repository_id, scenario_id, data_mode, "
                "title, repository, author, commit_sha, branch, created_at, "
                "deployment_status, deployment_environment, changed_services, "
                "files_changed, lines_added, lines_deleted, flags, test_coverage, "
                "rollback_ready, observability_score, previous_failures, risk, "
                "blast_radius"
                ") SELECT "
                "'rolling-change', workspace_id, repository_id, scenario_id, "
                "data_mode, title, repository, author, 'fedcba654321', branch, "
                "created_at, deployment_status, deployment_environment, "
                "changed_services, files_changed, lines_added, lines_deleted, "
                "flags, test_coverage, rollback_ready, observability_score, "
                "previous_failures, risk, blast_radius "
                "FROM changes WHERE id = 'legacy-change'"
            )
        )
        rolling_versions = connection.execute(
            text(
                "SELECT analysis_schema_version, engine_version, "
                "scoring_policy_version, graph_version "
                "FROM changes WHERE id = 'rolling-change'"
            )
        ).one()
        assert set(rolling_versions) == {LEGACY_ANALYSIS_VERSION}

    command.downgrade(config, "0007")
    inspector = inspect(database.engine)
    assert VERSION_COLUMNS.isdisjoint(
        column["name"] for column in inspector.get_columns("changes")
    )
    assert VERSION_COLUMNS.isdisjoint(
        column["name"] for column in inspector.get_columns("incidents")
    )
    with database.engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM changes")) == 2
        assert connection.scalar(text("SELECT COUNT(*) FROM incidents")) == 1
        assert "overall_score" in str(
            connection.scalar(
                text("SELECT risk FROM changes WHERE id = 'legacy-change'")
            )
        )

    command.upgrade(config, "0008")
    with database.engine.connect() as connection:
        values = connection.execute(
            text(
                "SELECT analysis_schema_version, engine_version, "
                "scoring_policy_version, graph_version "
                "FROM changes WHERE id = 'legacy-change'"
            )
        ).one()
        assert set(values) == {LEGACY_ANALYSIS_VERSION}


def test_analysis_snapshot_migration_backfills_and_downgrades_safely(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{(tmp_path / 'analysis-migration.db').as_posix()}"
    )
    try:
        _exercise_analysis_snapshot_migration(database)
    finally:
        database.dispose()


@pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DATABASE_URL"),
    reason="POSTGRES_TEST_DATABASE_URL is not configured",
)
def test_analysis_snapshot_migration_on_postgresql() -> None:
    database = Database(os.environ["POSTGRES_TEST_DATABASE_URL"])
    config = database._alembic_config()
    try:
        _exercise_analysis_snapshot_migration(database)
    finally:
        if "alembic_version" in inspect(database.engine).get_table_names():
            command.downgrade(config, "base")
        database.dispose()
