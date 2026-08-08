"""represent unknown connected change evidence without false sentinels

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("changes") as batch_op:
        batch_op.alter_column(
            "test_coverage",
            existing_type=sa.Float(),
            nullable=True,
        )
        batch_op.alter_column(
            "rollback_ready",
            existing_type=sa.Boolean(),
            nullable=True,
        )
        batch_op.alter_column(
            "observability_score",
            existing_type=sa.Float(),
            nullable=True,
        )
        batch_op.alter_column(
            "previous_failures",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    # The previous schema had no representation for unknown evidence. These
    # values are compatibility sentinels used only when rolling back the schema.
    op.execute(
        sa.text(
            "UPDATE changes SET "
            "test_coverage = COALESCE(test_coverage, 0), "
            "rollback_ready = COALESCE(rollback_ready, false), "
            "observability_score = COALESCE(observability_score, 0), "
            "previous_failures = COALESCE(previous_failures, 0)"
        )
    )
    with op.batch_alter_table("changes") as batch_op:
        batch_op.alter_column(
            "test_coverage",
            existing_type=sa.Float(),
            nullable=False,
        )
        batch_op.alter_column(
            "rollback_ready",
            existing_type=sa.Boolean(),
            nullable=False,
        )
        batch_op.alter_column(
            "observability_score",
            existing_type=sa.Float(),
            nullable=False,
        )
        batch_op.alter_column(
            "previous_failures",
            existing_type=sa.Integer(),
            nullable=False,
        )
