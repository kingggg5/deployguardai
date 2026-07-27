from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
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

