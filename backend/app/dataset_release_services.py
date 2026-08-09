"""Tenant-scoped, append-only dataset release registry operations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .dataset_models import DatasetReleaseRecord, DatasetReleaseRevocation
from .dataset_safety import leakage_findings, redact_payload
from .errors import DomainError
from .models import User
from .schemas import (
    ActorProvenance,
    DatasetReleaseCreate,
    DatasetReleaseRevocationRequest,
    DatasetReleaseRevocationSummary,
    DatasetReleaseSummary,
)
from .workspace_services import audit, membership_for


def _actor(user: User) -> ActorProvenance:
    return ActorProvenance(
        user_id=user.id,
        display_name=user.display_name,
        auth_provider=user.auth_provider,
        recorded_at=datetime.now(UTC),
    )


def _summary(
    record: DatasetReleaseRecord,
    *,
    revoked: bool,
) -> DatasetReleaseSummary:
    return DatasetReleaseSummary(
        id=record.id,
        workspace_id=record.workspace_id,
        release_version=record.release_version,
        purpose=record.purpose,
        status="revoked" if revoked else record.status,
        bundle_sha256=record.bundle_sha256,
        source_snapshot_count=record.source_snapshot_count,
        manifest=record.manifest,
        created_by=ActorProvenance(
            user_id=record.created_by_user_id,
            display_name=record.created_by_display_name,
            auth_provider=record.created_by_auth_provider,
            recorded_at=record.created_at,
        ),
        created_at=record.created_at,
    )


def _revoked_release_ids(session: Session, release_ids: Iterable[str]) -> set[str]:
    ids = list(release_ids)
    if not ids:
        return set()
    return set(
        session.scalars(
            select(DatasetReleaseRevocation.release_id).where(
                DatasetReleaseRevocation.release_id.in_(ids)
            )
        )
    )


def list_dataset_releases(
    session: Session,
    user: User,
    workspace_id: str,
) -> list[DatasetReleaseSummary]:
    membership_for(session, user, workspace_id)
    records = session.scalars(
        select(DatasetReleaseRecord)
        .where(DatasetReleaseRecord.workspace_id == workspace_id)
        .order_by(DatasetReleaseRecord.created_at.desc(), DatasetReleaseRecord.id.desc())
    ).all()
    revoked = _revoked_release_ids(session, [record.id for record in records])
    return [_summary(record, revoked=record.id in revoked) for record in records]


def create_dataset_release(
    session: Session,
    user: User,
    workspace_id: str,
    payload: DatasetReleaseCreate,
    *,
    request_id: str,
) -> DatasetReleaseSummary:
    membership_for(session, user, workspace_id, "admin")
    sanitized, redactions = redact_payload(payload.manifest)
    if redactions:
        raise DomainError(
            "Dataset manifest contains redaction findings; review it before registration",
            "dataset_release_redaction_required",
            422,
        )
    records = payload.manifest.get("records") if isinstance(payload.manifest, dict) else None
    if isinstance(records, list):
        leakage = leakage_findings(
            [item for item in records if isinstance(item, dict)]
        )
        if leakage:
            raise DomainError(
                "Dataset manifest contains duplicate examples across frozen splits",
                "dataset_release_leakage_detected",
                422,
            )
    existing = session.scalar(
        select(DatasetReleaseRecord).where(
            DatasetReleaseRecord.workspace_id == workspace_id,
            DatasetReleaseRecord.release_version == payload.release_version,
        )
    )
    if existing is not None:
        raise DomainError(
            "Dataset release version already exists in this workspace",
            "dataset_release_version_conflict",
            409,
        )
    now = datetime.now(UTC)
    record = DatasetReleaseRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        release_version=payload.release_version,
        purpose=payload.purpose,
        status=payload.status,
        bundle_sha256=payload.bundle_sha256.lower(),
        source_snapshot_count=payload.source_snapshot_count,
        manifest=sanitized,
        created_by_user_id=user.id,
        created_by_display_name=user.display_name,
        created_by_auth_provider=user.auth_provider,
        created_at=now,
    )
    session.add(record)
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="dataset.release.registered",
        resource_type="dataset_release",
        resource_id=record.id,
        request_id=request_id,
        metadata={
            "release_version": record.release_version,
            "purpose": record.purpose,
            "status": record.status,
            "bundle_sha256": record.bundle_sha256,
        },
    )
    session.commit()
    return _summary(record, revoked=False)


def revoke_dataset_release(
    session: Session,
    user: User,
    workspace_id: str,
    release_id: str,
    payload: DatasetReleaseRevocationRequest,
    *,
    request_id: str,
) -> DatasetReleaseRevocationSummary:
    membership_for(session, user, workspace_id, "admin")
    record = session.scalar(
        select(DatasetReleaseRecord).where(
            DatasetReleaseRecord.id == release_id,
            DatasetReleaseRecord.workspace_id == workspace_id,
        )
    )
    if record is None:
        raise DomainError("Dataset release not found", "dataset_release_not_found", 404)
    if session.scalar(
        select(DatasetReleaseRevocation).where(
            DatasetReleaseRevocation.release_id == record.id
        )
    ) is not None:
        raise DomainError(
            "Dataset release is already revoked",
            "dataset_release_already_revoked",
            409,
        )
    now = datetime.now(UTC)
    material = {
        "release_id": record.id,
        "bundle_sha256": record.bundle_sha256,
        "reason": payload.reason.strip(),
        "actor_user_id": user.id,
        "created_at": now.isoformat(),
    }
    tombstone = hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    revocation = DatasetReleaseRevocation(
        id=str(uuid4()),
        workspace_id=workspace_id,
        release_id=record.id,
        reason=payload.reason.strip(),
        tombstone_sha256=tombstone,
        actor_user_id=user.id,
        actor_display_name=user.display_name,
        actor_auth_provider=user.auth_provider,
        created_at=now,
    )
    session.add(revocation)
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="dataset.release.revoked",
        resource_type="dataset_release",
        resource_id=record.id,
        request_id=request_id,
        metadata={"tombstone_sha256": tombstone, "reason": payload.reason},
    )
    session.commit()
    return DatasetReleaseRevocationSummary(
        release_id=record.id,
        tombstone_sha256=tombstone,
        reason=revocation.reason,
        actor=_actor(user),
        created_at=now,
    )
