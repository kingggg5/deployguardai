"""add canonical provider-backed deployments

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("repository_id", sa.String(36), nullable=False),
        sa.Column("change_id", sa.String(80), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_deployment_id", sa.String(160), nullable=False),
        sa.Column("environment", sa.String(80), nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("ref", sa.String(160), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_url", sa.String(2_048), nullable=True),
        sa.Column("service_ids", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=True),
        sa.Column(
            "provider_created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "provider_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"]),
        sa.ForeignKeyConstraint(
            ["last_event_id"],
            ["operational_events.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "provider_deployment_id",
            name="uq_deployment_workspace_provider_identity",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'queued', 'in_progress', 'succeeded', 'failed', "
            "'cancelled', 'inactive', 'unknown'"
            ")",
            name="ck_deployment_status",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_deployment_version",
        ),
    )
    for column in (
        "workspace_id",
        "repository_id",
        "change_id",
        "provider",
        "provider_deployment_id",
        "environment",
        "commit_sha",
        "status",
        "last_event_id",
        "provider_created_at",
    ):
        op.create_index(
            f"ix_deployments_{column}",
            "deployments",
            [column],
        )
    op.create_index(
        "ix_deployments_workspace_created",
        "deployments",
        ["workspace_id", "provider_created_at"],
    )
    op.create_index(
        "ix_deployments_repository_commit",
        "deployments",
        ["repository_id", "commit_sha"],
    )
    op.create_index(
        "ix_deployments_workspace_environment_status",
        "deployments",
        ["workspace_id", "environment", "status"],
    )


def downgrade() -> None:
    for name in (
        "ix_deployments_workspace_environment_status",
        "ix_deployments_repository_commit",
        "ix_deployments_workspace_created",
        "ix_deployments_provider_created_at",
        "ix_deployments_last_event_id",
        "ix_deployments_status",
        "ix_deployments_commit_sha",
        "ix_deployments_environment",
        "ix_deployments_provider_deployment_id",
        "ix_deployments_provider",
        "ix_deployments_change_id",
        "ix_deployments_repository_id",
        "ix_deployments_workspace_id",
    ):
        op.drop_index(name, table_name="deployments")
    op.drop_table("deployments")
