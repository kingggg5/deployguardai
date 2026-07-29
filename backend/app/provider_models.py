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


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "provider", name="uq_workspace_provider_connection"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    installation_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    external_account_id: Mapped[str] = mapped_column(String(120))
    external_account_login: Mapped[str] = mapped_column(String(240))
    external_account_type: Mapped[str] = mapped_column(String(40))
    connection_state: Mapped[str] = mapped_column(String(24), index=True)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON)
    repository_selection: Mapped[str] = mapped_column(String(24))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ProviderAuthorizationState(Base):
    __tablename__ = "provider_authorization_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("provider", "delivery_id", name="uq_provider_delivery"),
        Index("ix_webhook_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    delivery_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(100))
    installation_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GitHubCheckPublication(Base):
    __tablename__ = "github_check_publications"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "head_sha",
            name="uq_github_check_repository_head",
        ),
        Index(
            "ix_github_check_workspace_status",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_github_check_retry_due",
            "status",
            "next_retry_at",
        ),
        CheckConstraint(
            "status IN ("
            "'pending', 'publishing', 'published', "
            "'retryable_failed', 'permanent_failed'"
            ")",
            name="ck_github_check_publication_status",
        ),
        CheckConstraint(
            "conclusion IS NULL OR conclusion IN ('neutral', 'success')",
            name="ck_github_check_publication_conclusion",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_github_check_publication_attempt_count",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"), index=True
    )
    change_id: Mapped[str] = mapped_column(
        ForeignKey("changes.id"), index=True
    )
    head_sha: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(160))
    provider_check_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    conclusion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details_url: Mapped[str] = mapped_column(String(2_048))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InvitationDelivery(Base):
    __tablename__ = "invitation_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invitation_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_invitations.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), index=True)
    provider_message_id: Mapped[str | None] = mapped_column(
        String(240), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
