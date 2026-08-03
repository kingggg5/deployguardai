"""add durable background job outbox

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(120), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(160), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_background_job_idempotency"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter')",
            name="ck_background_job_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_background_job_attempts"),
        sa.CheckConstraint(
            "max_attempts >= 1", name="ck_background_job_max_attempts"
        ),
    )
    for column in (
        "workspace_id",
        "idempotency_key",
        "status",
        "available_at",
        "request_id",
        "created_at",
    ):
        op.create_index(
            f"ix_background_jobs_{column}", "background_jobs", [column]
        )
    op.create_index(
        "ix_background_jobs_ready",
        "background_jobs",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_background_jobs_type_status",
        "background_jobs",
        ["job_type", "status"],
    )
    op.create_index(
        "ix_background_jobs_workspace_created",
        "background_jobs",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    for name in (
        "ix_background_jobs_workspace_created",
        "ix_background_jobs_type_status",
        "ix_background_jobs_ready",
        "ix_background_jobs_created_at",
        "ix_background_jobs_request_id",
        "ix_background_jobs_available_at",
        "ix_background_jobs_status",
        "ix_background_jobs_idempotency_key",
        "ix_background_jobs_workspace_id",
    ):
        op.drop_index(name, table_name="background_jobs")
    op.drop_table("background_jobs")
