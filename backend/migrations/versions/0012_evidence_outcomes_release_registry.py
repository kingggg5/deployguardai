"""add authenticated receipts, explicit deployment outcomes, and release registry

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DIRECT_TENANT_TABLES = (
    "verification_receipts",
    "dataset_release_registry",
    "dataset_release_revocations",
)
_IMMUTABLE_TABLES = (
    "verification_receipts",
    "dataset_release_registry",
    "dataset_release_revocations",
)
_POLICY_NAME = "deployguard_workspace_isolation"
_WORKSPACE_EXPRESSION = (
    "workspace_id = NULLIF("
    "current_setting('deployguard.workspace_id', true), ''"
    ")"
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _create_policy(table_name: str) -> None:
    if not _is_postgresql():
        return
    op.execute(
        sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_POLICY_NAME}" ON "{table_name}" '
            f"FOR ALL USING ({_WORKSPACE_EXPRESSION}) "
            f"WITH CHECK ({_WORKSPACE_EXPRESSION})"
        )
    )


def _create_immutability_guard(table_name: str) -> None:
    if _is_postgresql():
        op.execute(
            sa.text(
                f'CREATE TRIGGER "{table_name}_immutable" '
                f'BEFORE UPDATE OR DELETE ON "{table_name}" '
                "FOR EACH ROW EXECUTE FUNCTION "
                "deployguard_reject_immutable_mutation()"
            )
        )
        return
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f'CREATE TRIGGER "{table_name}_no_{operation.lower()}" '
                f'BEFORE {operation} ON "{table_name}" '
                "BEGIN SELECT RAISE(ABORT, "
                "'DeployGuard immutable record cannot be changed'); END"
            )
        )


def upgrade() -> None:
    with op.batch_alter_table("github_check_publications") as batch_op:
        batch_op.drop_constraint(
            "ck_github_check_publication_conclusion", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_github_check_publication_conclusion",
            "conclusion IS NULL OR conclusion IN ('neutral', 'failure', 'success')",
        )

    with op.batch_alter_table("deployments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "outcome_state",
                sa.String(24),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "outcome_evidence",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column("outcome_incident_id", sa.String(80), nullable=True)
        )
        batch_op.add_column(
            sa.Column("outcome_confirmed_by_user_id", sa.String(36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("outcome_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_deployments_outcome_incident",
            "incidents",
            ["outcome_incident_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_deployments_outcome_user",
            "users",
            ["outcome_confirmed_by_user_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_deployment_outcome_state",
            "outcome_state IN ('unknown', 'stable_window_met', 'failed', "
            "'rolled_back', 'incident_linked')",
        )
        batch_op.create_index(
            "ix_deployments_outcome_state",
            ["outcome_state"],
        )

    op.create_table(
        "verification_receipts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("repository_id", sa.String(36), nullable=False),
        sa.Column("change_id", sa.String(80), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("attestation_state", sa.String(16), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("attestation", sa.JSON(), nullable=True),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_sha256", name="uq_verification_receipt_sha"),
        sa.CheckConstraint(
            "decision IN ('pass', 'review', 'block', 'error')",
            name="ck_verification_receipt_decision",
        ),
        sa.CheckConstraint(
            "attestation_state IN ('verified', 'missing', 'invalid')",
            name="ck_verification_receipt_attestation_state",
        ),
    )
    for name, columns in (
        ("ix_verification_receipts_workspace_id", ["workspace_id"]),
        ("ix_verification_receipts_repository_id", ["repository_id"]),
        ("ix_verification_receipts_change_id", ["change_id"]),
        ("ix_verification_receipts_head_sha", ["head_sha"]),
        ("ix_verification_receipts_created", ["workspace_id", "created_at"]),
        ("ix_verification_receipts_repository_head", ["repository_id", "head_sha"]),
    ):
        op.create_index(name, "verification_receipts", columns)

    op.create_table(
        "dataset_release_registry",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("release_version", sa.String(80), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("bundle_sha256", sa.String(64), nullable=False),
        sa.Column("source_snapshot_count", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_by_display_name", sa.String(160), nullable=False),
        sa.Column("created_by_auth_provider", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "release_version",
            name="uq_dataset_release_workspace_version",
        ),
        sa.UniqueConstraint("bundle_sha256", name="uq_dataset_release_bundle_sha"),
        sa.CheckConstraint(
            "purpose IN ('evaluation', 'training')",
            name="ck_dataset_release_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('ready_for_review', 'published', 'revoked')",
            name="ck_dataset_release_status",
        ),
    )
    op.create_index(
        "ix_dataset_release_registry_workspace",
        "dataset_release_registry",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "dataset_release_revocations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("release_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.String(2_000), nullable=False),
        sa.Column("tombstone_sha256", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("actor_display_name", sa.String(160), nullable=False),
        sa.Column("actor_auth_provider", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["release_id"], ["dataset_release_registry.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tombstone_sha256", name="uq_dataset_release_tombstone_sha"),
    )
    op.create_index(
        "ix_dataset_release_revocations_workspace",
        "dataset_release_revocations",
        ["workspace_id", "created_at"],
    )

    for table_name in _DIRECT_TENANT_TABLES:
        _create_policy(table_name)
        _create_immutability_guard(table_name)


def downgrade() -> None:
    for table_name in reversed(_IMMUTABLE_TABLES):
        if _is_postgresql():
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
                    f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'
                )
            )
        else:
            for operation in ("update", "delete"):
                op.execute(
                    sa.text(
                        f'DROP TRIGGER IF EXISTS "{table_name}_no_{operation}"'
                    )
                )

    op.drop_index(
        "ix_dataset_release_revocations_workspace",
        table_name="dataset_release_revocations",
    )
    op.drop_table("dataset_release_revocations")
    op.drop_index(
        "ix_dataset_release_registry_workspace",
        table_name="dataset_release_registry",
    )
    op.drop_table("dataset_release_registry")
    for name in (
        "ix_verification_receipts_repository_head",
        "ix_verification_receipts_created",
        "ix_verification_receipts_head_sha",
        "ix_verification_receipts_change_id",
        "ix_verification_receipts_repository_id",
        "ix_verification_receipts_workspace_id",
    ):
        op.drop_index(name, table_name="verification_receipts")
    op.drop_table("verification_receipts")

    with op.batch_alter_table("deployments") as batch_op:
        batch_op.drop_index("ix_deployments_outcome_state")
        batch_op.drop_constraint("ck_deployment_outcome_state", type_="check")
        batch_op.drop_constraint("fk_deployments_outcome_user", type_="foreignkey")
        batch_op.drop_constraint("fk_deployments_outcome_incident", type_="foreignkey")
        for column in (
            "outcome_confirmed_at",
            "outcome_confirmed_by_user_id",
            "outcome_incident_id",
            "outcome_evidence",
            "outcome_state",
        ):
            batch_op.drop_column(column)

    with op.batch_alter_table("github_check_publications") as batch_op:
        batch_op.drop_constraint(
            "ck_github_check_publication_conclusion", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_github_check_publication_conclusion",
            "conclusion IS NULL OR conclusion IN ('neutral', 'success')",
        )
