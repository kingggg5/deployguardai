from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class DeploymentRecord(Base):
    """Canonical, provider-backed deployment state.

    ChangeRecord remains the immutable risk-analysis snapshot. This record
    tracks the deployment lifecycle separately while retaining an optional,
    deterministic link to the analyzed change that has the same repository
    and commit SHA.
    """

    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            "provider_deployment_id",
            name="uq_deployment_workspace_provider_identity",
        ),
        CheckConstraint(
            "status IN ("
            "'queued', 'in_progress', 'succeeded', 'failed', "
            "'cancelled', 'inactive', 'unknown'"
            ")",
            name="ck_deployment_status",
        ),
        CheckConstraint(
            "outcome_state IN ("
            "'unknown', 'stable_window_met', 'failed', "
            "'rolled_back', 'incident_linked'"
            ")",
            name="ck_deployment_outcome_state",
        ),
        CheckConstraint("version >= 1", name="ck_deployment_version"),
        Index(
            "ix_deployments_workspace_created",
            "workspace_id",
            "provider_created_at",
        ),
        Index(
            "ix_deployments_repository_commit",
            "repository_id",
            "commit_sha",
        ),
        Index(
            "ix_deployments_workspace_environment_status",
            "workspace_id",
            "environment",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"), index=True
    )
    change_id: Mapped[str | None] = mapped_column(
        ForeignKey("changes.id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    provider_deployment_id: Mapped[str] = mapped_column(
        String(160), index=True
    )
    environment: Mapped[str] = mapped_column(String(80), index=True)
    commit_sha: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    outcome_state: Mapped[str] = mapped_column(
        String(24), default="unknown", server_default="unknown", index=True
    )
    outcome_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    outcome_incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    outcome_confirmed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    outcome_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_url: Mapped[str | None] = mapped_column(
        String(2_048), nullable=True
    )
    service_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("operational_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    provider_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
