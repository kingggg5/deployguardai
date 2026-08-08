"""Authenticated, exact-SHA verification receipts.

Receipts are immutable facts produced outside the API.  The API stores the
canonical document and only uses a receipt after its HMAC, content hash, head
SHA, and optional attestation have all passed validation.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class VerificationReceiptRecord(Base):
    __tablename__ = "verification_receipts"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('pass', 'review', 'block', 'error')",
            name="ck_verification_receipt_decision",
        ),
        CheckConstraint(
            "attestation_state IN ('verified', 'missing', 'invalid')",
            name="ck_verification_receipt_attestation_state",
        ),
        Index(
            "ix_verification_receipts_workspace_created",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_verification_receipts_repository_head",
            "repository_id",
            "head_sha",
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
    receipt_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    head_sha: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    attestation_state: Mapped[str] = mapped_column(String(16), index=True)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON)
    attestation: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(80), default="github_action")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
