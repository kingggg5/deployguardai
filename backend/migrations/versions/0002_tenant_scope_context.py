"""add tenant scope and per-user context

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-28
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_USER_ID = "00000000-0000-0000-0000-000000000001"
LEGACY_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"
LEGACY_REPOSITORY_ID = "00000000-0000-0000-0000-000000000003"
LEGACY_MEMBERSHIP_ID = "00000000-0000-0000-0000-000000000004"


def _insert_legacy_scope() -> None:
    connection = op.get_bind()
    timestamp = datetime.now(UTC)
    if connection.execute(
        sa.text("SELECT 1 FROM users WHERE id = :id"),
        {"id": LEGACY_USER_ID},
    ).scalar_one_or_none() is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO users (
                    id, email, display_name, auth_provider,
                    provider_subject, is_active, created_at
                ) VALUES (
                    :id, :email, :display_name, :auth_provider,
                    :provider_subject, :is_active, :created_at
                )
                """
            ),
            {
                "id": LEGACY_USER_ID,
                "email": "migration@deployguard.invalid",
                "display_name": "Legacy migration principal",
                "auth_provider": "system",
                "provider_subject": "system:legacy-migration",
                "is_active": False,
                "created_at": timestamp,
            },
        )
    if connection.execute(
        sa.text("SELECT 1 FROM workspaces WHERE id = :id"),
        {"id": LEGACY_WORKSPACE_ID},
    ).scalar_one_or_none() is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO workspaces (
                    id, name, slug, created_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :name, :slug, :created_by_user_id,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "id": LEGACY_WORKSPACE_ID,
                "name": "DeployGuard synthetic demo",
                "slug": "deployguard-synthetic-demo",
                "created_by_user_id": LEGACY_USER_ID,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
    if connection.execute(
        sa.text("SELECT 1 FROM repositories WHERE id = :id"),
        {"id": LEGACY_REPOSITORY_ID},
    ).scalar_one_or_none() is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO repositories (
                    id, workspace_id, provider, provider_repository_id,
                    full_name, default_branch, visibility, connection_state,
                    data_mode, selected, last_synced_at, created_at
                ) VALUES (
                    :id, :workspace_id, :provider, :provider_repository_id,
                    :full_name, :default_branch, :visibility,
                    :connection_state, :data_mode, :selected,
                    :last_synced_at, :created_at
                )
                """
            ),
            {
                "id": LEGACY_REPOSITORY_ID,
                "workspace_id": LEGACY_WORKSPACE_ID,
                "provider": "development",
                "provider_repository_id": "fixture:deployguard-synthetic-demo",
                "full_name": "deployguard/synthetic-demo",
                "default_branch": "main",
                "visibility": "private",
                "connection_state": "connected",
                "data_mode": "synthetic",
                "selected": True,
                "last_synced_at": timestamp,
                "created_at": timestamp,
            },
        )
    if connection.execute(
        sa.text("SELECT 1 FROM workspace_memberships WHERE id = :id"),
        {"id": LEGACY_MEMBERSHIP_ID},
    ).scalar_one_or_none() is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO workspace_memberships (
                    id, workspace_id, user_id, role, joined_at
                ) VALUES (
                    :id, :workspace_id, :user_id, :role, :joined_at
                )
                """
            ),
            {
                "id": LEGACY_MEMBERSHIP_ID,
                "workspace_id": LEGACY_WORKSPACE_ID,
                "user_id": LEGACY_USER_ID,
                "role": "owner",
                "joined_at": timestamp,
            },
        )


def _add_scope(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(
            sa.Column(
                "workspace_id",
                sa.String(length=36),
                nullable=False,
                server_default=LEGACY_WORKSPACE_ID,
            )
        )
        batch_op.add_column(
            sa.Column(
                "repository_id",
                sa.String(length=36),
                nullable=False,
                server_default=LEGACY_REPOSITORY_ID,
            )
        )
        batch_op.create_foreign_key(
            f"fk_{table_name}_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            f"fk_{table_name}_repository_id",
            "repositories",
            ["repository_id"],
            ["id"],
        )
        batch_op.create_index(
            f"ix_{table_name}_workspace_id", ["workspace_id"]
        )
        batch_op.create_index(
            f"ix_{table_name}_repository_id", ["repository_id"]
        )
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column("workspace_id", server_default=None)
        batch_op.alter_column("repository_id", server_default=None)


def upgrade() -> None:
    _insert_legacy_scope()
    _add_scope("scenarios")
    _add_scope("changes")
    _add_scope("incidents")
    op.create_table(
        "user_contexts",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=36), nullable=True),
        sa.Column("scenario_id", sa.String(length=80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    with op.batch_alter_table("user_contexts") as batch_op:
        batch_op.create_index(
            "ix_user_contexts_workspace_id", ["workspace_id"]
        )
        batch_op.create_index(
            "ix_user_contexts_repository_id", ["repository_id"]
        )
        batch_op.create_index(
            "ix_user_contexts_scenario_id", ["scenario_id"]
        )


def _drop_scope(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_index(f"ix_{table_name}_repository_id")
        batch_op.drop_index(f"ix_{table_name}_workspace_id")
        batch_op.drop_constraint(
            f"fk_{table_name}_repository_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            f"fk_{table_name}_workspace_id", type_="foreignkey"
        )
        batch_op.drop_column("repository_id")
        batch_op.drop_column("workspace_id")


def downgrade() -> None:
    with op.batch_alter_table("user_contexts") as batch_op:
        batch_op.drop_index("ix_user_contexts_scenario_id")
        batch_op.drop_index("ix_user_contexts_repository_id")
        batch_op.drop_index("ix_user_contexts_workspace_id")
    op.drop_table("user_contexts")
    _drop_scope("incidents")
    _drop_scope("changes")
    _drop_scope("scenarios")
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM workspace_memberships WHERE id = :id"),
        {"id": LEGACY_MEMBERSHIP_ID},
    )
    connection.execute(
        sa.text("DELETE FROM repositories WHERE id = :id"),
        {"id": LEGACY_REPOSITORY_ID},
    )
    connection.execute(
        sa.text("DELETE FROM workspaces WHERE id = :id"),
        {"id": LEGACY_WORKSPACE_ID},
    )
    connection.execute(
        sa.text("DELETE FROM users WHERE id = :id"),
        {"id": LEGACY_USER_ID},
    )
