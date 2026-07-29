from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ServiceCatalogEntry(Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "slug", name="uq_service_workspace_slug"
        ),
        CheckConstraint(
            "tier IN ('tier_1', 'tier_2', 'tier_3', 'tier_4')",
            name="ck_service_tier",
        ),
        CheckConstraint(
            "lifecycle IN ('active', 'deprecated', 'experimental')",
            name="ck_service_lifecycle",
        ),
        Index("ix_services_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    tier: Mapped[str] = mapped_column(String(20))
    lifecycle: Mapped[str] = mapped_column(String(24))
    owner_team: Mapped[str] = mapped_column(String(160))
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id"), nullable=True, index=True
    )
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    runbook_url: Mapped[str | None] = mapped_column(
        String(2_048), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkspaceRiskPolicy(Base):
    __tablename__ = "workspace_risk_policies"
    __table_args__ = (
        CheckConstraint(
            "warn_threshold >= 0 AND warn_threshold <= 100",
            name="ck_risk_policy_warn_threshold",
        ),
        CheckConstraint(
            "block_threshold >= 0 AND block_threshold <= 100",
            name="ck_risk_policy_block_threshold",
        ),
        CheckConstraint(
            "warn_threshold < block_threshold",
            name="ck_risk_policy_threshold_order",
        ),
        CheckConstraint(
            "max_blast_radius >= 1",
            name="ck_risk_policy_blast_radius",
        ),
        CheckConstraint("version >= 1", name="ck_risk_policy_version"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    warn_threshold: Mapped[int] = mapped_column(Integer, default=60)
    block_threshold: Mapped[int] = mapped_column(Integer, default=80)
    require_tests: Mapped[bool] = mapped_column(Boolean, default=True)
    require_rollback: Mapped[bool] = mapped_column(Boolean, default=True)
    max_blast_radius: Mapped[int] = mapped_column(Integer, default=10)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperationalEvent(Base):
    __tablename__ = "operational_events"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source",
            "provider_event_id",
            name="uq_operational_event_provider",
        ),
        CheckConstraint(
            "severity IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="ck_operational_event_severity",
        ),
        CheckConstraint(
            "ingestion_status IN ('accepted', 'correlated')",
            name="ck_operational_event_ingestion_status",
        ),
        Index(
            "ix_operational_events_workspace_occurred",
            "workspace_id",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_event_id: Mapped[str] = mapped_column(String(160))
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id"), nullable=True, index=True
    )
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("services.id"), nullable=True, index=True
    )
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    severity: Mapped[str] = mapped_column(String(20), index=True)
    summary: Mapped[str] = mapped_column(String(1_000))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ingestion_status: Mapped[str] = mapped_column(String(24), index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('incident_lifecycle', 'incident_note')",
            name="ck_notification_kind",
        ),
        Index(
            "ix_notifications_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_notifications_user_read",
            "user_id",
            "read_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240))
    message: Mapped[str] = mapped_column(String(1_000))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(160), index=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
