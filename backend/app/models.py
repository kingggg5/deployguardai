from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


LEGACY_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"
LEGACY_REPOSITORY_ID = "00000000-0000-0000-0000-000000000003"


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        default=LEGACY_WORKSPACE_ID,
        index=True,
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"),
        default=LEGACY_REPOSITORY_ID,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    data_mode: Mapped[str] = mapped_column(String(20), default="synthetic")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active_change_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    active_incident_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    service_graph: Mapped[dict[str, Any]] = mapped_column(JSON)


class ChangeRecord(Base):
    __tablename__ = "changes"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        default=LEGACY_WORKSPACE_ID,
        index=True,
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"),
        default=LEGACY_REPOSITORY_ID,
        index=True,
    )
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id"), index=True
    )
    data_mode: Mapped[str] = mapped_column(String(20), default="synthetic")
    title: Mapped[str] = mapped_column(String(240))
    repository: Mapped[str] = mapped_column(String(240))
    author: Mapped[str] = mapped_column(String(160))
    commit_sha: Mapped[str] = mapped_column(String(64))
    branch: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deployment_status: Mapped[str] = mapped_column(String(40))
    deployment_environment: Mapped[str] = mapped_column(String(80))
    changed_services: Mapped[list[str]] = mapped_column(JSON)
    files_changed: Mapped[int] = mapped_column(Integer)
    lines_added: Mapped[int] = mapped_column(Integer)
    lines_deleted: Mapped[int] = mapped_column(Integer)
    flags: Mapped[list[str]] = mapped_column(JSON)
    test_coverage: Mapped[float] = mapped_column(Float)
    rollback_ready: Mapped[bool] = mapped_column(Boolean)
    observability_score: Mapped[float] = mapped_column(Float)
    previous_failures: Mapped[int] = mapped_column(Integer)
    risk: Mapped[dict[str, Any]] = mapped_column(JSON)
    blast_radius: Mapped[dict[str, Any]] = mapped_column(JSON)


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        default=LEGACY_WORKSPACE_ID,
        index=True,
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"),
        default=LEGACY_REPOSITORY_ID,
        index=True,
    )
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id"), index=True
    )
    data_mode: Mapped[str] = mapped_column(String(20), default="synthetic")
    title: Mapped[str] = mapped_column(String(240))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    affected_services: Mapped[list[str]] = mapped_column(JSON)
    correlated_change_id: Mapped[str | None] = mapped_column(
        ForeignKey("changes.id"), nullable=True, index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    hypotheses: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


class FeedbackRecord(Base):
    __tablename__ = "incident_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id"), index=True
    )
    hypothesis_id: Mapped[str] = mapped_column(String(100))
    verdict: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    auth_provider: Mapped[str] = mapped_column(String(40))
    provider_subject: Mapped[str] = mapped_column(String(240), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["WorkspaceMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["WorkspaceMembership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    repositories: Mapped[list["Repository"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class UserContext(Base):
    __tablename__ = "user_contexts"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id"), nullable=True, index=True
    )
    scenario_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenarios.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessToken(Base):
    __tablename__ = "access_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            "provider_repository_id",
            name="uq_workspace_provider_repository",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_repository_id: Mapped[str] = mapped_column(String(160))
    full_name: Mapped[str] = mapped_column(String(240))
    default_branch: Mapped[str] = mapped_column(String(160))
    visibility: Mapped[str] = mapped_column(String(20))
    connection_state: Mapped[str] = mapped_column(String(24))
    data_mode: Mapped[str] = mapped_column(String(20))
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[Workspace] = relationship(back_populates="repositories")


class Invitation(Base):
    __tablename__ = "workspace_invitations"
    __table_args__ = (
        Index(
            "ix_pending_invitation_workspace_email",
            "workspace_id",
            "email",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    invited_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(160))
    request_id: Mapped[str] = mapped_column(String(80))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
