from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
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
