"""Restore a backup into an isolated disposable target and verify it.

SQLite rehearsals always restore into a temporary directory. PostgreSQL
rehearsals require an explicit disposable database name, a destructive-action
confirmation, and a non-target administrative connection. The script refuses
database names outside the ``deployguard_restore_*`` namespace.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from typing import Any

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

try:
    from scripts.restore_check import verify_postgres_archive, verify_sqlite
except ModuleNotFoundError:  # direct ``python scripts/restore_rehearsal.py``
    from restore_check import verify_postgres_archive, verify_sqlite


POSTGRES_CONFIRMATION = "CREATE-AND-DROP-ISOLATED-DATABASE"
SAFE_DATABASE_NAME = re.compile(r"^deployguard_restore_[a-z0-9_]{1,40}$")
REQUIRED_TABLES = {
    "access_tokens", "audit_events", "background_jobs", "changes",
    "deployments", "github_check_publications", "incident_feedback",
    "incidents", "invitation_deliveries", "notifications",
    "operational_events", "provider_authorization_states",
    "provider_connections", "repositories", "scenarios", "services",
    "user_contexts", "users", "webhook_deliveries",
    "workspace_invitations", "workspace_memberships",
    "workspace_risk_policies", "workspaces",
}
RLS_TABLES = {
    "repositories", "scenarios", "changes", "incidents", "audit_events",
    "services", "workspace_risk_policies", "operational_events",
    "deployments", "incident_feedback",
}


def rehearse_sqlite(
    backup: Path,
    *,
    expected_head: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    backup = backup.resolve()
    verify_sqlite(backup, expected_head=expected_head)
    with tempfile.TemporaryDirectory(prefix="deployguard-restore-") as temp:
        restored = Path(temp) / "restored.db"
        shutil.copy2(backup, restored)
        connection = sqlite3.connect(restored)
        try:
            connection.execute(
                "CREATE TABLE __restore_rehearsal (checked_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO __restore_rehearsal VALUES (?)",
                (datetime.now(UTC).isoformat(),),
            )
            connection.commit()
            assert connection.execute(
                "SELECT COUNT(*) FROM __restore_rehearsal"
            ).fetchone()[0] == 1
            integrity = str(
                connection.execute("PRAGMA integrity_check").fetchone()[0]
            )
        finally:
            connection.close()
    if integrity != "ok":
        raise RuntimeError(f"Restored SQLite integrity check failed: {integrity}")
    return {
        "format": "sqlite",
        "source": str(backup),
        "isolated_target": True,
        "write_probe": True,
        "integrity": integrity,
        "expected_head": expected_head,
        "duration_ms": round((time.perf_counter() - started) * 1_000, 3),
    }


def _pg_restore_command(
    admin_database_url: str,
    target_database: str,
    backup: Path,
) -> tuple[list[str], dict[str, str]]:
    parsed = make_url(admin_database_url)
    target_url = URL.create(
        drivername="postgresql",
        username=parsed.username,
        host=parsed.host,
        port=parsed.port,
        database=target_database,
        query=parsed.query,
    ).render_as_string(hide_password=False)
    command = [
        "pg_restore", "--exit-on-error", "--no-owner", "--no-acl",
        "--dbname", target_url, str(backup),
    ]
    environment = os.environ.copy()
    if parsed.password:
        environment["PGPASSWORD"] = parsed.password
    return command, environment


def _apply_runtime_grants(
    admin_database_url: str,
    *,
    target_database: str,
    schema_owner: str,
    application_role: str,
) -> None:
    parsed = make_url(admin_database_url)
    target_url = URL.create(
        drivername="postgresql",
        username=parsed.username,
        host=parsed.host,
        port=parsed.port,
        database=target_database,
        query=parsed.query,
    ).render_as_string(hide_password=False)
    grant_file = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "postgres"
        / "runtime-role-grants.sql"
    )
    environment = os.environ.copy()
    if parsed.password:
        environment["PGPASSWORD"] = parsed.password
    result = subprocess.run(
        [
            "psql", "--dbname", target_url,
            f"--set=schema_owner={schema_owner}",
            f"--set=application_role={application_role}",
            f"--file={grant_file}",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError("Runtime-role grants failed on the restored target")


def rehearse_postgres(
    backup: Path,
    *,
    admin_database_url: str,
    target_database: str,
    confirmation: str,
    expected_head: str,
    application_database_url: str,
) -> dict[str, Any]:
    if confirmation != POSTGRES_CONFIRMATION:
        raise ValueError(
            f"PostgreSQL rehearsal requires --confirm {POSTGRES_CONFIRMATION}"
        )
    if not SAFE_DATABASE_NAME.fullmatch(target_database):
        raise ValueError(
            "Target database must match deployguard_restore_[a-z0-9_]{1,40}"
        )
    backup = backup.resolve()
    verify_postgres_archive(backup)
    parsed = make_url(admin_database_url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        raise ValueError("A PostgreSQL administrative database URL is required")
    if parsed.database == target_database:
        raise ValueError("Administrative database must differ from restore target")
    if not parsed.username:
        raise ValueError("Administrative database URL must include schema owner")
    application_parsed = make_url(application_database_url)
    if (
        application_parsed.get_backend_name() != "postgresql"
        or not application_parsed.username
    ):
        raise ValueError("A PostgreSQL application database URL is required")

    started = time.perf_counter()
    created = False
    connection_url = parsed.set(database=target_database).render_as_string(
        hide_password=False
    )
    psycopg_admin_url = admin_database_url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(psycopg_admin_url, autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (target_database,),
        ).fetchone()
        if exists:
            raise RuntimeError(
                f"Disposable restore database already exists: {target_database}"
            )
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database))
        )
        created = True
    try:
        command, environment = _pg_restore_command(
            admin_database_url,
            target_database,
            backup,
        )
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if result.returncode != 0:
            raise RuntimeError("pg_restore failed against the isolated target")
        _apply_runtime_grants(
            admin_database_url,
            target_database=target_database,
            schema_owner=parsed.username,
            application_role=application_parsed.username,
        )
        engine = create_engine(connection_url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                head = connection.scalar(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                table_count = int(
                    connection.scalar(
                        text(
                            "SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema = 'public'"
                        )
                    )
                    or 0
                )
                table_names = set(
                    connection.scalars(
                        text(
                            "SELECT tablename FROM pg_tables "
                            "WHERE schemaname = current_schema()"
                        )
                    )
                )
                missing_tables = REQUIRED_TABLES - table_names
                if missing_tables:
                    raise RuntimeError(
                        "Restored schema is missing required tables: "
                        + ", ".join(sorted(missing_tables))
                    )
                invalid_constraints = int(
                    connection.scalar(
                        text(
                            "SELECT COUNT(*) FROM pg_constraint c "
                            "JOIN pg_namespace n ON n.oid = c.connamespace "
                            "WHERE n.nspname = current_schema() "
                            "AND NOT c.convalidated"
                        )
                    )
                    or 0
                )
                if invalid_constraints:
                    raise RuntimeError(
                        "Restored schema contains unvalidated constraints"
                    )
                connection.execute(
                    text(
                        "CREATE TABLE __restore_rehearsal "
                        "(checked_at TIMESTAMPTZ NOT NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO __restore_rehearsal VALUES (CURRENT_TIMESTAMP)")
                )
            if head != expected_head:
                raise RuntimeError(
                    f"Restored schema head is {head!r}; expected {expected_head!r}"
                )
        finally:
            engine.dispose()
        runtime_url = application_parsed.set(
            database=target_database
        ).render_as_string(hide_password=False)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        try:
            with runtime_engine.connect() as connection:
                posture = connection.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                        "FROM pg_roles WHERE rolname = current_user"
                    )
                ).mappings().one()
                if any(bool(value) for value in posture.values()):
                    raise RuntimeError("Restored runtime role is privileged")
                rls_tables = set(
                    connection.scalars(
                        text(
                            "SELECT c.relname FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid = c.relnamespace "
                            "WHERE n.nspname = current_schema() "
                            "AND c.relrowsecurity "
                            "AND EXISTS (SELECT 1 FROM pg_policies p "
                            "WHERE p.schemaname = n.nspname "
                            "AND p.tablename = c.relname "
                            "AND p.policyname = "
                            "'deployguard_workspace_isolation')"
                        )
                    )
                )
                if rls_tables != RLS_TABLES:
                    raise RuntimeError("Restored RLS policy coverage is incomplete")
                for table in sorted(RLS_TABLES):
                    quoted = connection.dialect.identifier_preparer.quote(table)
                    visible = int(
                        connection.scalar(text(f"SELECT COUNT(*) FROM {quoted}"))
                        or 0
                    )
                    if visible:
                        raise RuntimeError(
                            "Restored RLS did not fail closed without tenant context"
                        )
        finally:
            runtime_engine.dispose()
        return {
            "format": "postgresql-custom",
            "source": str(backup),
            "isolated_target": target_database,
            "write_probe": True,
            "alembic_head": head,
            "table_count": table_count,
            "required_tables": len(REQUIRED_TABLES),
            "validated_constraints": True,
            "runtime_role_probe": True,
            "rls_policy_tables": len(RLS_TABLES),
            "duration_ms": round((time.perf_counter() - started) * 1_000, 3),
        }
    finally:
        if created:
            with psycopg.connect(psycopg_admin_url, autocommit=True) as admin:
                admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (target_database,),
                )
                admin.execute(
                    sql.SQL("DROP DATABASE {}").format(
                        sql.Identifier(target_database)
                    )
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument(
        "--format",
        choices=("auto", "sqlite", "postgresql-custom"),
        default="auto",
    )
    parser.add_argument("--expected-head")
    parser.add_argument(
        "--admin-database-url",
        default=os.getenv("RESTORE_ADMIN_DATABASE_URL", ""),
    )
    parser.add_argument("--target-database")
    parser.add_argument(
        "--application-database-url",
        default=os.getenv("RESTORE_APPLICATION_DATABASE_URL", ""),
        help="Non-owner runtime role URL used for post-restore RLS probes",
    )
    parser.add_argument("--confirm")
    parser.add_argument("--report", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        backup_format = args.format
        if backup_format == "auto":
            backup_format = (
                "sqlite"
                if args.backup.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
                else "postgresql-custom"
            )
        if backup_format == "sqlite":
            result = rehearse_sqlite(
                args.backup,
                expected_head=args.expected_head,
            )
        else:
            if (
                not args.admin_database_url
                or not args.application_database_url
                or not args.target_database
                or not args.expected_head
            ):
                raise ValueError(
                    "PostgreSQL rehearsal requires admin/application URLs, "
                    "--target-database, and --expected-head"
                )
            result = rehearse_postgres(
                args.backup,
                admin_database_url=args.admin_database_url,
                target_database=args.target_database,
                confirmation=args.confirm or "",
                expected_head=args.expected_head,
                application_database_url=args.application_database_url,
            )
        payload = {
            "success": True,
            "completed_at": datetime.now(UTC).isoformat(),
            **result,
        }
        output = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        print(output)
        if args.report:
            report = args.report.resolve()
            report.parent.mkdir(parents=True, exist_ok=True)
            if report.exists():
                raise FileExistsError(f"Report already exists: {report}")
            report.write_text(output + "\n", encoding="utf-8")
        return 0
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"restore_rehearsal_failed: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
