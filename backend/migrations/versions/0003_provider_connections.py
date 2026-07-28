"""add source-control and invitation delivery records

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("installation_id", sa.String(80), nullable=False),
        sa.Column("external_account_id", sa.String(120), nullable=False),
        sa.Column("external_account_login", sa.String(240), nullable=False),
        sa.Column("external_account_type", sa.String(40), nullable=False),
        sa.Column("connection_state", sa.String(24), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("repository_selection", sa.String(24), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "workspace_id", "provider", name="uq_workspace_provider_connection"
        ),
        sa.UniqueConstraint("installation_id"),
    )
    op.create_index(
        "ix_provider_connections_workspace_id",
        "provider_connections",
        ["workspace_id"],
    )
    op.create_index(
        "ix_provider_connections_provider",
        "provider_connections",
        ["provider"],
    )
    op.create_index(
        "ix_provider_connections_installation_id",
        "provider_connections",
        ["installation_id"],
    )
    op.create_index(
        "ix_provider_connections_connection_state",
        "provider_connections",
        ["connection_state"],
    )

    op.create_table(
        "provider_authorization_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("state_hash"),
    )
    for column in ("state_hash", "workspace_id", "user_id", "expires_at"):
        op.create_index(
            f"ix_provider_authorization_states_{column}",
            "provider_authorization_states",
            [column],
        )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("delivery_id", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("installation_id", sa.String(80), nullable=True),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("repository_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.UniqueConstraint(
            "provider", "delivery_id", name="uq_provider_delivery"
        ),
    )
    op.create_index(
        "ix_webhook_workspace_created",
        "webhook_deliveries",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_webhook_deliveries_installation_id",
        "webhook_deliveries",
        ["installation_id"],
    )
    for column in ("workspace_id", "repository_id", "status"):
        op.create_index(
            f"ix_webhook_deliveries_{column}",
            "webhook_deliveries",
            [column],
        )

    op.create_table(
        "invitation_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invitation_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_message_id", sa.String(240), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["invitation_id"], ["workspace_invitations.id"]
        ),
    )
    op.create_index(
        "ix_invitation_deliveries_invitation_id",
        "invitation_deliveries",
        ["invitation_id"],
    )
    op.create_index(
        "ix_invitation_deliveries_status",
        "invitation_deliveries",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_invitation_deliveries_status",
        table_name="invitation_deliveries",
    )
    op.drop_index(
        "ix_invitation_deliveries_invitation_id",
        table_name="invitation_deliveries",
    )
    op.drop_table("invitation_deliveries")
    for name in (
        "ix_webhook_deliveries_status",
        "ix_webhook_deliveries_repository_id",
        "ix_webhook_deliveries_workspace_id",
        "ix_webhook_deliveries_installation_id",
        "ix_webhook_workspace_created",
    ):
        op.drop_index(name, table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    for column in ("expires_at", "user_id", "workspace_id", "state_hash"):
        op.drop_index(
            f"ix_provider_authorization_states_{column}",
            table_name="provider_authorization_states",
        )
    op.drop_table("provider_authorization_states")
    for name in (
        "ix_provider_connections_connection_state",
        "ix_provider_connections_installation_id",
        "ix_provider_connections_provider",
        "ix_provider_connections_workspace_id",
    ):
        op.drop_index(name, table_name="provider_connections")
    op.drop_table("provider_connections")
