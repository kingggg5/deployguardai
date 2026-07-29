"""add production operations domain records

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("lifecycle", sa.String(24), nullable=False),
        sa.Column("owner_team", sa.String(160), nullable=False),
        sa.Column("repository_id", sa.String(36), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("runbook_url", sa.String(2_048), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.CheckConstraint(
            "tier IN ('tier_1', 'tier_2', 'tier_3', 'tier_4')",
            name="ck_service_tier",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('active', 'deprecated', 'experimental')",
            name="ck_service_lifecycle",
        ),
        sa.UniqueConstraint(
            "workspace_id", "slug", name="uq_service_workspace_slug"
        ),
    )
    for column in ("workspace_id", "repository_id", "created_at"):
        op.create_index(
            f"ix_services_{column}", "services", [column]
        )
    op.create_index(
        "ix_services_workspace_created",
        "services",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "workspace_risk_policies",
        sa.Column("workspace_id", sa.String(36), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("warn_threshold", sa.Integer(), nullable=False),
        sa.Column("block_threshold", sa.Integer(), nullable=False),
        sa.Column("require_tests", sa.Boolean(), nullable=False),
        sa.Column("require_rollback", sa.Boolean(), nullable=False),
        sa.Column("max_blast_radius", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.CheckConstraint(
            "warn_threshold >= 0 AND warn_threshold <= 100",
            name="ck_risk_policy_warn_threshold",
        ),
        sa.CheckConstraint(
            "block_threshold >= 0 AND block_threshold <= 100",
            name="ck_risk_policy_block_threshold",
        ),
        sa.CheckConstraint(
            "warn_threshold < block_threshold",
            name="ck_risk_policy_threshold_order",
        ),
        sa.CheckConstraint(
            "max_blast_radius >= 1",
            name="ck_risk_policy_blast_radius",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_risk_policy_version"
        ),
    )

    op.create_table(
        "operational_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_event_id", sa.String(160), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("repository_id", sa.String(36), nullable=True),
        sa.Column("service_id", sa.String(36), nullable=True),
        sa.Column("incident_id", sa.String(80), nullable=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("summary", sa.String(1_000), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("ingestion_status", sa.String(24), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.CheckConstraint(
            "severity IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="ck_operational_event_severity",
        ),
        sa.CheckConstraint(
            "ingestion_status IN ('accepted', 'correlated')",
            name="ck_operational_event_ingestion_status",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source",
            "provider_event_id",
            name="uq_operational_event_provider",
        ),
    )
    for column in (
        "workspace_id",
        "repository_id",
        "service_id",
        "incident_id",
        "source",
        "event_type",
        "occurred_at",
        "severity",
        "ingestion_status",
        "ingested_at",
    ):
        op.create_index(
            f"ix_operational_events_{column}",
            "operational_events",
            [column],
        )
    op.create_index(
        "ix_operational_events_workspace_occurred",
        "operational_events",
        ["workspace_id", "occurred_at"],
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("message", sa.String(1_000), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(160), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.CheckConstraint(
            "kind IN ('incident_lifecycle', 'incident_note')",
            name="ck_notification_kind",
        ),
    )
    for column in (
        "workspace_id",
        "user_id",
        "kind",
        "resource_id",
        "read_at",
        "created_at",
    ):
        op.create_index(
            f"ix_notifications_{column}", "notifications", [column]
        )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_user_read",
        "notifications",
        ["user_id", "read_at"],
    )

    with op.batch_alter_table("incidents") as batch_op:
        batch_op.add_column(
            sa.Column("assignee_user_id", sa.String(36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_incidents_assignee_user",
            "users",
            ["assignee_user_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_incidents_assignee_user_id", ["assignee_user_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("incidents") as batch_op:
        batch_op.drop_index("ix_incidents_assignee_user_id")
        batch_op.drop_constraint(
            "fk_incidents_assignee_user", type_="foreignkey"
        )
        batch_op.drop_column("assignee_user_id")

    for name in (
        "ix_notifications_user_read",
        "ix_notifications_user_created",
        "ix_notifications_created_at",
        "ix_notifications_read_at",
        "ix_notifications_resource_id",
        "ix_notifications_kind",
        "ix_notifications_user_id",
        "ix_notifications_workspace_id",
    ):
        op.drop_index(name, table_name="notifications")
    op.drop_table("notifications")

    for name in (
        "ix_operational_events_workspace_occurred",
        "ix_operational_events_ingested_at",
        "ix_operational_events_ingestion_status",
        "ix_operational_events_severity",
        "ix_operational_events_occurred_at",
        "ix_operational_events_event_type",
        "ix_operational_events_source",
        "ix_operational_events_incident_id",
        "ix_operational_events_service_id",
        "ix_operational_events_repository_id",
        "ix_operational_events_workspace_id",
    ):
        op.drop_index(name, table_name="operational_events")
    op.drop_table("operational_events")
    op.drop_table("workspace_risk_policies")

    for name in (
        "ix_services_workspace_created",
        "ix_services_created_at",
        "ix_services_repository_id",
        "ix_services_workspace_id",
    ):
        op.drop_index(name, table_name="services")
    op.drop_table("services")
