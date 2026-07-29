"""add durable GitHub Check publication records

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "github_check_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("repository_id", sa.String(36), nullable=False),
        sa.Column("change_id", sa.String(80), nullable=False),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("provider_check_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("conclusion", sa.String(32), nullable=True),
        sa.Column("details_url", sa.String(2_048), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"]),
        sa.UniqueConstraint(
            "repository_id",
            "head_sha",
            name="uq_github_check_repository_head",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'pending', 'publishing', 'published', "
            "'retryable_failed', 'permanent_failed'"
            ")",
            name="ck_github_check_publication_status",
        ),
        sa.CheckConstraint(
            "conclusion IS NULL OR conclusion IN ('neutral', 'success')",
            name="ck_github_check_publication_conclusion",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_github_check_publication_attempt_count",
        ),
    )
    for column in (
        "workspace_id",
        "repository_id",
        "change_id",
        "provider_check_id",
        "status",
        "next_retry_at",
    ):
        op.create_index(
            f"ix_github_check_publications_{column}",
            "github_check_publications",
            [column],
        )
    op.create_index(
        "ix_github_check_workspace_status",
        "github_check_publications",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_github_check_retry_due",
        "github_check_publications",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    for name in (
        "ix_github_check_retry_due",
        "ix_github_check_workspace_status",
        "ix_github_check_publications_next_retry_at",
        "ix_github_check_publications_status",
        "ix_github_check_publications_provider_check_id",
        "ix_github_check_publications_change_id",
        "ix_github_check_publications_repository_id",
        "ix_github_check_publications_workspace_id",
    ):
        op.drop_index(name, table_name="github_check_publications")
    op.drop_table("github_check_publications")
