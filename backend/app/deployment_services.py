from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .deployment_models import DeploymentRecord
from .deployment_schemas import DeploymentResponse
from .errors import DomainError
from .models import ChangeRecord, Repository, User
from .operations_models import ServiceCatalogEntry
from .operations_schemas import OperationalEventResponse
from .workspace_services import audit, membership_for, new_id, now_utc


GITHUB_DEPLOYMENT_STATUS = {
    "created": "queued",
    "queued": "queued",
    "pending": "queued",
    "in_progress": "in_progress",
    "success": "succeeded",
    "failure": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "inactive": "inactive",
}

LEGACY_DEPLOYMENT_STATUS = {
    "queued": "pending",
    "in_progress": "in_progress",
    "succeeded": "deployed",
    "failed": "failed",
    "cancelled": "cancelled",
    "inactive": "inactive",
    "unknown": "unknown",
}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_timestamp(value: object, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return _utc(value) or fallback
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
        return _utc(parsed) or fallback
    return fallback


def deployment_response(record: DeploymentRecord) -> DeploymentResponse:
    return DeploymentResponse.model_validate(
        {
            "id": record.id,
            "workspace_id": record.workspace_id,
            "repository_id": record.repository_id,
            "change_id": record.change_id,
            "provider": record.provider,
            "provider_deployment_id": record.provider_deployment_id,
            "environment": record.environment,
            "commit_sha": record.commit_sha,
            "ref": record.ref,
            "status": record.status,
            "provider_url": record.provider_url,
            "service_ids": record.service_ids,
            "last_event_id": record.last_event_id,
            "provider_created_at": _utc(record.provider_created_at),
            "provider_updated_at": _utc(record.provider_updated_at),
            "finished_at": _utc(record.finished_at),
            "version": record.version,
            "created_at": _utc(record.created_at),
            "updated_at": _utc(record.updated_at),
        }
    )


def _matched_change(
    session: Session,
    *,
    workspace_id: str,
    repository_id: str,
    commit_sha: str | None,
    occurred_at: datetime,
) -> ChangeRecord | None:
    if not commit_sha:
        return None
    statement = (
        select(ChangeRecord)
        .where(
            ChangeRecord.workspace_id == workspace_id,
            ChangeRecord.repository_id == repository_id,
            func.lower(ChangeRecord.commit_sha) == commit_sha.lower(),
        )
        .order_by(ChangeRecord.created_at.desc(), ChangeRecord.id.desc())
    )
    candidates = session.scalars(statement).all()
    eligible = [
        candidate
        for candidate in candidates
        if (_utc(candidate.created_at) or occurred_at) <= occurred_at
    ]
    return eligible[0] if eligible else None


def _service_ids(
    session: Session,
    *,
    workspace_id: str,
    repository_id: str,
    change: ChangeRecord | None,
) -> list[str]:
    records = session.scalars(
        select(ServiceCatalogEntry)
        .where(
            ServiceCatalogEntry.workspace_id == workspace_id,
            ServiceCatalogEntry.repository_id == repository_id,
        )
        .order_by(ServiceCatalogEntry.id)
    ).all()
    by_id = {record.id: record for record in records}
    changed = [
        reference
        for reference in (change.changed_services if change else [])
        if reference in by_id
    ]
    return list(dict.fromkeys(changed or list(by_id)))


def upsert_github_deployment(
    session: Session,
    *,
    payload: dict[str, Any],
    workspace_id: str,
    repository: Repository,
    operational_event: OperationalEventResponse,
    delivery_id: str,
    _retry_on_conflict: bool = True,
) -> DeploymentResponse | None:
    deployment = payload.get("deployment")
    if not isinstance(deployment, dict):
        return None
    provider_deployment_id = str(deployment.get("id") or "").strip()
    if not provider_deployment_id:
        return None

    status_payload = payload.get("deployment_status")
    if not isinstance(status_payload, dict):
        status_payload = {}
    raw_status = str(
        status_payload.get("state")
        or deployment.get("state")
        or payload.get("action")
        or "unknown"
    ).strip().lower()
    normalized_status = GITHUB_DEPLOYMENT_STATUS.get(raw_status, "unknown")
    event_time = _utc(operational_event.occurred_at) or now_utc()
    provider_created_at = _parse_timestamp(
        deployment.get("created_at"),
        event_time,
    )
    provider_updated_at = _parse_timestamp(
        status_payload.get("created_at")
        or deployment.get("updated_at"),
        event_time,
    )
    commit_sha = str(
        deployment.get("sha")
        or status_payload.get("sha")
        or ""
    ).strip()[:64] or None
    ref = str(deployment.get("ref") or "").strip()[:160] or None
    environment = str(
        deployment.get("environment")
        or status_payload.get("environment")
        or "unknown"
    ).strip()[:80] or "unknown"
    provider_url = str(
        status_payload.get("environment_url")
        or status_payload.get("log_url")
        or deployment.get("url")
        or ""
    ).strip()[:2_048] or None
    matched_change = _matched_change(
        session,
        workspace_id=workspace_id,
        repository_id=repository.id,
        commit_sha=commit_sha,
        occurred_at=provider_updated_at,
    )
    services = _service_ids(
        session,
        workspace_id=workspace_id,
        repository_id=repository.id,
        change=matched_change,
    )
    record = session.scalar(
        select(DeploymentRecord).where(
            DeploymentRecord.workspace_id == workspace_id,
            DeploymentRecord.provider == "github",
            DeploymentRecord.provider_deployment_id
            == provider_deployment_id,
        )
    )
    if (
        record is not None
        and (record.provenance or {}).get("last_delivery_id") == delivery_id
    ):
        return deployment_response(record)
    if (
        record is not None
        and provider_updated_at
        < (_utc(record.provider_updated_at) or provider_updated_at)
    ):
        return deployment_response(record)
    timestamp = now_utc()
    created = record is None
    if record is None:
        record = DeploymentRecord(
            id=new_id(),
            workspace_id=workspace_id,
            repository_id=repository.id,
            change_id=matched_change.id if matched_change else None,
            provider="github",
            provider_deployment_id=provider_deployment_id,
            environment=environment,
            commit_sha=commit_sha,
            ref=ref,
            status=normalized_status,
            provider_url=provider_url,
            service_ids=services,
            provenance={
                "provider": "github",
                "installation_id": operational_event.provenance.get(
                    "installation_id"
                ),
                "provider_repository_id": (
                    repository.provider_repository_id
                ),
                "last_delivery_id": delivery_id,
            },
            last_event_id=operational_event.id,
            provider_created_at=provider_created_at,
            provider_updated_at=provider_updated_at,
            finished_at=(
                provider_updated_at
                if normalized_status
                in {"succeeded", "failed", "cancelled", "inactive"}
                else None
            ),
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(record)
    else:
        if (
            record.workspace_id != workspace_id
            or record.repository_id != repository.id
        ):
            raise DomainError(
                "Deployment identity does not match its recorded scope",
                "deployment_identity_mismatch",
                409,
            )
        record.change_id = (
            matched_change.id if matched_change else record.change_id
        )
        record.environment = environment
        record.commit_sha = commit_sha or record.commit_sha
        record.ref = ref or record.ref
        record.status = normalized_status
        record.provider_url = provider_url or record.provider_url
        record.service_ids = services or record.service_ids
        record.last_event_id = operational_event.id
        record.provider_updated_at = provider_updated_at
        record.finished_at = (
            provider_updated_at
            if normalized_status
            in {"succeeded", "failed", "cancelled", "inactive"}
            else None
        )
        record.version += 1
        record.provenance = {
            **(record.provenance or {}),
            "last_delivery_id": delivery_id,
        }
        record.updated_at = timestamp

    if matched_change is not None:
        matched_change.deployment_environment = environment
        matched_change.deployment_status = LEGACY_DEPLOYMENT_STATUS[
            normalized_status
        ]

    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=None,
        action=(
            "deployment.created" if created else "deployment.updated"
        ),
        resource_type="deployment",
        resource_id=record.id,
        request_id=f"github:{delivery_id}",
        metadata={
            "provider": "github",
            "provider_deployment_id": provider_deployment_id,
            "status": normalized_status,
            "change_id": record.change_id,
        },
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(DeploymentRecord).where(
                DeploymentRecord.workspace_id == workspace_id,
                DeploymentRecord.provider == "github",
                DeploymentRecord.provider_deployment_id
                == provider_deployment_id,
            )
        )
        if existing is None:
            raise
        if not _retry_on_conflict:
            raise
        return upsert_github_deployment(
            session,
            payload=payload,
            workspace_id=workspace_id,
            repository=repository,
            operational_event=operational_event,
            delivery_id=delivery_id,
            _retry_on_conflict=False,
        )
    return deployment_response(record)


def list_deployments(
    session: Session,
    user: User,
    workspace_id: str,
    *,
    repository_id: str | None,
    environment: str | None,
    status: str | None,
    limit: int,
) -> list[DeploymentResponse]:
    membership_for(session, user, workspace_id)
    statement = select(DeploymentRecord).where(
        DeploymentRecord.workspace_id == workspace_id
    )
    if repository_id is not None:
        statement = statement.where(
            DeploymentRecord.repository_id == repository_id
        )
    if environment is not None:
        statement = statement.where(
            DeploymentRecord.environment == environment
        )
    if status is not None:
        statement = statement.where(DeploymentRecord.status == status)
    records = session.scalars(
        statement.order_by(
            DeploymentRecord.provider_updated_at.desc(),
            DeploymentRecord.id.desc(),
        ).limit(limit)
    ).all()
    return [deployment_response(record) for record in records]


def get_deployment(
    session: Session, user: User, deployment_id: str
) -> DeploymentResponse:
    record = session.get(DeploymentRecord, deployment_id)
    if record is None:
        raise DomainError("Deployment not found", "deployment_not_found", 404)
    membership_for(session, user, record.workspace_id)
    return deployment_response(record)
