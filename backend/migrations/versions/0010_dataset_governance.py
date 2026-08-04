"""add incident verdict provenance and dataset governance records

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_POLICY_NAME = "deployguard_workspace_isolation"
_WORKSPACE_EXPRESSION = (
    "workspace_id = NULLIF("
    "current_setting('deployguard.workspace_id', true), ''"
    ")"
)
_IMMUTABLE_TABLES = (
    "postmortem_snapshots",
    "dataset_consent_decisions",
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _create_postgresql_guards() -> None:
    for table_name in _IMMUTABLE_TABLES:
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'
            )
        )
        op.execute(
            sa.text(
                f'CREATE POLICY "{_POLICY_NAME}" ON "{table_name}" '
                f"FOR ALL USING ({_WORKSPACE_EXPRESSION}) "
                f"WITH CHECK ({_WORKSPACE_EXPRESSION})"
            )
        )
    op.execute(
        sa.text(
            "CREATE FUNCTION deployguard_reject_immutable_mutation() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'DeployGuard immutable record cannot be changed'; "
            "END; $$"
        )
    )
    for table_name in _IMMUTABLE_TABLES:
        op.execute(
            sa.text(
                f'CREATE TRIGGER "{table_name}_immutable" '
                f'BEFORE UPDATE OR DELETE ON "{table_name}" '
                "FOR EACH ROW EXECUTE FUNCTION "
                "deployguard_reject_immutable_mutation()"
            )
        )


def _create_sqlite_guards() -> None:
    for table_name in _IMMUTABLE_TABLES:
        for operation in ("UPDATE", "DELETE"):
            trigger_name = f"{table_name}_no_{operation.lower()}"
            op.execute(
                sa.text(
                    f'CREATE TRIGGER "{trigger_name}" '
                    f'BEFORE {operation} ON "{table_name}" '
                    "BEGIN SELECT RAISE(ABORT, "
                    "'DeployGuard immutable record cannot be changed'); END"
                )
            )


def upgrade() -> None:
    with op.batch_alter_table("incident_feedback") as batch_op:
        batch_op.add_column(
            sa.Column("actor_user_id", sa.String(36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("actor_display_name", sa.String(160), nullable=True)
        )
        batch_op.add_column(
            sa.Column("actor_auth_provider", sa.String(40), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "verification_result",
                sa.String(24),
                nullable=False,
                server_default="not_recorded",
            )
        )
        batch_op.add_column(
            sa.Column("verification_method", sa.String(160), nullable=True)
        )
        batch_op.add_column(
            sa.Column("verification_summary", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "verification_evidence_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.create_foreign_key(
            "fk_incident_feedback_actor_user",
            "users",
            ["actor_user_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_incident_feedback_actor_user_id",
            ["actor_user_id"],
        )

    op.create_table(
        "postmortem_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(80), nullable=False),
        sa.Column("snapshot_version", sa.String(40), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("source_feedback_count", sa.Integer(), nullable=False),
        sa.Column("analysis_schema_version", sa.String(80), nullable=False),
        sa.Column("engine_version", sa.String(80), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_by_display_name", sa.String(160), nullable=False),
        sa.Column("created_by_auth_provider", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "incident_id",
            "content_sha256",
            name="uq_postmortem_incident_content",
        ),
    )
    op.create_index(
        "ix_postmortem_snapshots_workspace_id",
        "postmortem_snapshots",
        ["workspace_id"],
    )
    op.create_index(
        "ix_postmortem_snapshots_incident_id",
        "postmortem_snapshots",
        ["incident_id"],
    )
    op.create_index(
        "ix_postmortem_snapshots_content_sha256",
        "postmortem_snapshots",
        ["content_sha256"],
    )
    op.create_index(
        "ix_postmortem_workspace_incident_created",
        "postmortem_snapshots",
        ["workspace_id", "incident_id", "created_at"],
    )

    op.create_table(
        "dataset_consent_decisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(80), nullable=False),
        sa.Column("postmortem_snapshot_id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("terms_version", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("attestations", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("actor_display_name", sa.String(160), nullable=False),
        sa.Column("actor_auth_provider", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(
            ["postmortem_snapshot_id"], ["postmortem_snapshots.id"]
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dataset_consent_decisions_workspace_id",
        "dataset_consent_decisions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_dataset_consent_decisions_incident_id",
        "dataset_consent_decisions",
        ["incident_id"],
    )
    op.create_index(
        "ix_dataset_consent_decisions_postmortem_snapshot_id",
        "dataset_consent_decisions",
        ["postmortem_snapshot_id"],
    )
    op.create_index(
        "ix_dataset_consent_decisions_purpose",
        "dataset_consent_decisions",
        ["purpose"],
    )
    op.create_index(
        "ix_dataset_consent_decisions_actor_user_id",
        "dataset_consent_decisions",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_dataset_consent_workspace_incident_created",
        "dataset_consent_decisions",
        ["workspace_id", "incident_id", "created_at"],
    )

    if _is_postgresql():
        _create_postgresql_guards()
    else:
        _create_sqlite_guards()


def downgrade() -> None:
    if _is_postgresql():
        for table_name in _IMMUTABLE_TABLES:
            op.execute(
                sa.text(
                    f'DROP TRIGGER IF EXISTS "{table_name}_immutable" '
                    f'ON "{table_name}"'
                )
            )
            op.execute(
                sa.text(
                    f'DROP POLICY IF EXISTS "{_POLICY_NAME}" '
                    f'ON "{table_name}"'
                )
            )
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS "
                "deployguard_reject_immutable_mutation()"
            )
        )
    else:
        for table_name in _IMMUTABLE_TABLES:
            for operation in ("update", "delete"):
                op.execute(
                    sa.text(
                        f'DROP TRIGGER IF EXISTS "{table_name}_no_{operation}"'
                    )
                )

    op.drop_table("dataset_consent_decisions")
    op.drop_table("postmortem_snapshots")

    with op.batch_alter_table("incident_feedback") as batch_op:
        batch_op.drop_index("ix_incident_feedback_actor_user_id")
        batch_op.drop_constraint(
            "fk_incident_feedback_actor_user", type_="foreignkey"
        )
        for column_name in (
            "verification_evidence_ids",
            "verification_summary",
            "verification_method",
            "verification_result",
            "actor_auth_provider",
            "actor_display_name",
            "actor_user_id",
        ):
            batch_op.drop_column(column_name)
