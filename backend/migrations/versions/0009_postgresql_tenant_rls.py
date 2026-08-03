"""add PostgreSQL tenant row-level security policies

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DIRECT_TENANT_TABLES = (
    "repositories",
    "scenarios",
    "changes",
    "incidents",
    "audit_events",
    "services",
    "workspace_risk_policies",
    "operational_events",
    "deployments",
)
_INDIRECT_TENANT_TABLES = ("incident_feedback",)
_POLICY_NAME = "deployguard_workspace_isolation"
_WORKSPACE_EXPRESSION = (
    "workspace_id = NULLIF("
    "current_setting('deployguard.workspace_id', true), ''"
    ")"
)
_FEEDBACK_EXPRESSION = (
    "EXISTS ("
    "SELECT 1 FROM incidents "
    "WHERE incidents.id = incident_feedback.incident_id "
    "AND incidents.workspace_id = NULLIF("
    "current_setting('deployguard.workspace_id', true), ''"
    ")"
    ")"
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _create_policy(table_name: str, expression: str) -> None:
    # Identifiers are static constants above; values are read from a
    # transaction-local PostgreSQL setting and are never interpolated here.
    # FORCE is intentionally not used: migrations remain an owner concern,
    # while the runtime API must connect as a non-owner/non-BYPASSRLS role.
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{_POLICY_NAME}" ON "{table_name}" '
            f"FOR ALL USING ({expression}) WITH CHECK ({expression})"
        )
    )


def upgrade() -> None:
    if not _is_postgresql():
        return
    for table_name in _DIRECT_TENANT_TABLES:
        _create_policy(table_name, _WORKSPACE_EXPRESSION)
    for table_name in _INDIRECT_TENANT_TABLES:
        _create_policy(table_name, _FEEDBACK_EXPRESSION)


def downgrade() -> None:
    if not _is_postgresql():
        return
    for table_name in reversed(
        _DIRECT_TENANT_TABLES + _INDIRECT_TENANT_TABLES
    ):
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "{_POLICY_NAME}" '
                f'ON "{table_name}"'
            )
        )
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'
            )
        )
