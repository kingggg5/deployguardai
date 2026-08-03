"""add analysis snapshot version metadata

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VERSION_COLUMNS = (
    "analysis_schema_version",
    "engine_version",
    "scoring_policy_version",
    "graph_version",
)


def upgrade() -> None:
    # The sentinel is deliberately not the current engine version: historical
    # rows predate version capture, so their exact provenance cannot be proven.
    # Keep the server default for one rolling-compatibility release so an older
    # writer fails safe to an explicit unversioned value during deployment.
    for table_name in ("changes", "incidents"):
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in _VERSION_COLUMNS:
                batch_op.add_column(
                    sa.Column(
                        column_name,
                        sa.String(80),
                        nullable=False,
                        server_default="legacy-unversioned",
                    )
                )


def downgrade() -> None:
    for table_name in ("incidents", "changes"):
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in reversed(_VERSION_COLUMNS):
                batch_op.drop_column(column_name)
