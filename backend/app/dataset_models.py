"""Append-only dataset release records and consent revocation tombstones."""

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


class DatasetReleaseRecord(Base):
    __tablename__ = "dataset_release_registry"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "release_version",
            name="uq_dataset_release_workspace_version",
        ),
        CheckConstraint(
            "purpose IN ('evaluation', 'training')",
            name="ck_dataset_release_purpose",
        ),
        CheckConstraint(
            "status IN ('ready_for_review', 'published', 'revoked')",
            name="ck_dataset_release_status",
        ),
        Index(
            "ix_dataset_release_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    release_version: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), index=True)
    bundle_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    source_snapshot_count: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_by_display_name: Mapped[str] = mapped_column(String(160))
    created_by_auth_provider: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DatasetReleaseRevocation(Base):
    __tablename__ = "dataset_release_revocations"
    __table_args__ = (
        Index(
            "ix_dataset_release_revocations_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    release_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_release_registry.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(2_000))
    tombstone_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actor_display_name: Mapped[str] = mapped_column(String(160))
    actor_auth_provider: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
