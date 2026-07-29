import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .errors import DomainError
from .models import (
    IncidentRecord,
    Repository,
    User,
    WorkspaceMembership,
)
from .operations_models import (
    Notification,
    OperationalEvent,
    ServiceCatalogEntry,
    WorkspaceRiskPolicy,
)
from .operations_schemas import (
    IncidentLifecycleResponse,
    IncidentLifecycleUpdate,
    IncidentNoteCreate,
    ManualOperationalEventCreate,
    NotificationResponse,
    OperationalEventCreate,
    OperationalEventResponse,
    RiskPolicyResponse,
    RiskPolicyUpdate,
    ServiceCreate,
    ServiceResponse,
    ServiceUpdate,
)
from .schemas import TimelineEvent
from .workspace_services import audit, membership_for, new_id, now_utc


DEFAULT_RISK_POLICY = {
    "enabled": True,
    "warn_threshold": 60,
    "block_threshold": 80,
    "require_tests": True,
    "require_rollback": True,
    "max_blast_radius": 10,
}
INCIDENT_STATUS_ORDER = {
    "open": 0,
    "acknowledged": 1,
    "investigating": 2,
    "mitigated": 3,
    "resolved": 4,
}
RESERVED_PROVIDER_SOURCE_NAMESPACES = frozenset(
    {"github", "telemetry", "otel", "otlp", "opentelemetry"}
)


def _service_response(record: ServiceCatalogEntry) -> ServiceResponse:
    return ServiceResponse.model_validate(record)


def _risk_policy_response(record: WorkspaceRiskPolicy) -> RiskPolicyResponse:
    return RiskPolicyResponse.model_validate(record)


def _event_response(record: OperationalEvent) -> OperationalEventResponse:
    occurred_at = record.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    ingested_at = record.ingested_at
    if ingested_at.tzinfo is None:
        ingested_at = ingested_at.replace(tzinfo=UTC)
    return OperationalEventResponse.model_validate(
        {
            "id": record.id,
            "provider_event_id": record.provider_event_id,
            "workspace_id": record.workspace_id,
            "repository_id": record.repository_id,
            "service_id": record.service_id,
            "incident_id": record.incident_id,
            "source": record.source,
            "event_type": record.event_type,
            "occurred_at": occurred_at,
            "severity": record.severity,
            "summary": record.summary,
            "attributes": record.attributes,
            "provenance": record.provenance,
            "ingestion_status": record.ingestion_status,
            "ingested_at": ingested_at,
        }
    )


def _notification_response(record: Notification) -> NotificationResponse:
    return NotificationResponse.model_validate(record)


def _repository_for_workspace(
    session: Session, workspace_id: str, repository_id: str | None
) -> Repository | None:
    if repository_id is None:
        return None
    repository = session.scalar(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.workspace_id == workspace_id,
        )
    )
    if repository is None:
        raise DomainError(
            "Repository not found", "repository_not_found", 404
        )
    return repository


def _service_for_workspace(
    session: Session, workspace_id: str, service_id: str
) -> ServiceCatalogEntry:
    service = session.scalar(
        select(ServiceCatalogEntry).where(
            ServiceCatalogEntry.id == service_id,
            ServiceCatalogEntry.workspace_id == workspace_id,
        )
    )
    if service is None:
        raise DomainError("Service not found", "service_not_found", 404)
    return service


def _validate_service_dependencies(
    session: Session,
    workspace_id: str,
    service_id: str,
    dependencies: list[str],
) -> None:
    if service_id in dependencies:
        raise DomainError(
            "A service cannot depend on itself",
            "service_self_dependency",
            422,
        )
    services = session.scalars(
        select(ServiceCatalogEntry)
        .where(ServiceCatalogEntry.workspace_id == workspace_id)
        .with_for_update()
    ).all()
    graph = {item.id: list(item.dependencies or []) for item in services}
    dependency_ids = set(dependencies)
    if not dependency_ids.issubset(graph):
        raise DomainError(
            "Every dependency must reference a service in this workspace",
            "invalid_service_dependency",
            422,
        )
    graph[service_id] = dependencies
    state: dict[str, int] = {}

    def visit(node_id: str) -> None:
        node_state = state.get(node_id, 0)
        if node_state == 1:
            raise DomainError(
                "Service dependencies must not contain cycles",
                "service_dependency_cycle",
                422,
            )
        if node_state == 2:
            return
        state[node_id] = 1
        for dependency_id in graph.get(node_id, []):
            visit(dependency_id)
        state[node_id] = 2

    for current_id in graph:
        visit(current_id)


def list_services(
    session: Session, user: User, workspace_id: str
) -> list[ServiceResponse]:
    membership_for(session, user, workspace_id)
    records = session.scalars(
        select(ServiceCatalogEntry)
        .where(ServiceCatalogEntry.workspace_id == workspace_id)
        .order_by(ServiceCatalogEntry.name, ServiceCatalogEntry.id)
    ).all()
    return [_service_response(item) for item in records]


def create_service(
    session: Session,
    user: User,
    workspace_id: str,
    payload: ServiceCreate,
    request_id: str,
) -> ServiceResponse:
    membership_for(session, user, workspace_id, "admin")
    slug = payload.slug.strip().lower()
    if session.scalar(
        select(ServiceCatalogEntry.id).where(
            ServiceCatalogEntry.workspace_id == workspace_id,
            ServiceCatalogEntry.slug == slug,
        )
    ):
        raise DomainError(
            "Service slug is already in use",
            "service_slug_exists",
            409,
        )
    _repository_for_workspace(session, workspace_id, payload.repository_id)
    service_id = new_id()
    _validate_service_dependencies(
        session, workspace_id, service_id, payload.dependencies
    )
    timestamp = now_utc()
    record = ServiceCatalogEntry(
        id=service_id,
        workspace_id=workspace_id,
        name=payload.name.strip(),
        slug=slug,
        description=payload.description.strip(),
        tier=payload.tier,
        lifecycle=payload.lifecycle,
        owner_team=payload.owner_team.strip(),
        repository_id=payload.repository_id,
        dependencies=payload.dependencies,
        runbook_url=payload.runbook_url,
        tags=payload.tags,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(record)
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="service.created",
        resource_type="service",
        resource_id=record.id,
        request_id=request_id,
        metadata={"slug": slug},
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError(
            "Service slug is already in use",
            "service_slug_exists",
            409,
        ) from exc
    return _service_response(record)


def get_service(
    session: Session, user: User, service_id: str
) -> ServiceResponse:
    record = session.get(ServiceCatalogEntry, service_id)
    if record is None:
        raise DomainError("Service not found", "service_not_found", 404)
    membership_for(session, user, record.workspace_id)
    return _service_response(record)


def update_service(
    session: Session,
    user: User,
    service_id: str,
    payload: ServiceUpdate,
    request_id: str,
) -> ServiceResponse:
    record = session.get(ServiceCatalogEntry, service_id)
    if record is None:
        raise DomainError("Service not found", "service_not_found", 404)
    membership_for(session, user, record.workspace_id, "admin")
    changes = payload.model_dump(exclude_unset=True)
    if "slug" in changes and changes["slug"] is not None:
        changes["slug"] = changes["slug"].strip().lower()
        conflicting_id = session.scalar(
            select(ServiceCatalogEntry.id).where(
                ServiceCatalogEntry.workspace_id == record.workspace_id,
                ServiceCatalogEntry.slug == changes["slug"],
                ServiceCatalogEntry.id != record.id,
            )
        )
        if conflicting_id is not None:
            raise DomainError(
                "Service slug is already in use",
                "service_slug_exists",
                409,
            )
    if "repository_id" in changes:
        _repository_for_workspace(
            session, record.workspace_id, changes["repository_id"]
        )
    if "dependencies" in changes and changes["dependencies"] is not None:
        _validate_service_dependencies(
            session,
            record.workspace_id,
            record.id,
            changes["dependencies"],
        )
    for field, value in changes.items():
        if field in {"name", "owner_team"} and value is not None:
            value = value.strip()
        if field == "description" and value is not None:
            value = value.strip()
        setattr(record, field, value)
    record.updated_at = now_utc()
    audit(
        session,
        workspace_id=record.workspace_id,
        actor_user_id=user.id,
        action="service.updated",
        resource_type="service",
        resource_id=record.id,
        request_id=request_id,
        metadata={"fields": sorted(changes)},
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError(
            "Service slug is already in use",
            "service_slug_exists",
            409,
        ) from exc
    return _service_response(record)


def get_risk_policy(
    session: Session, user: User, workspace_id: str
) -> RiskPolicyResponse:
    membership_for(session, user, workspace_id)
    record = session.get(WorkspaceRiskPolicy, workspace_id)
    if record is None:
        timestamp = now_utc()
        record = WorkspaceRiskPolicy(
            workspace_id=workspace_id,
            **DEFAULT_RISK_POLICY,
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            record = session.get(WorkspaceRiskPolicy, workspace_id)
            if record is None:
                raise
    return _risk_policy_response(record)


def update_risk_policy(
    session: Session,
    user: User,
    workspace_id: str,
    payload: RiskPolicyUpdate,
    request_id: str,
) -> RiskPolicyResponse:
    membership_for(session, user, workspace_id, "admin")
    record = session.get(WorkspaceRiskPolicy, workspace_id)
    if record is None:
        timestamp = now_utc()
        record = WorkspaceRiskPolicy(
            workspace_id=workspace_id,
            **DEFAULT_RISK_POLICY,
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(record)
        session.flush()
    expected_version = record.version + 1
    if payload.version != expected_version:
        raise DomainError(
            f"Risk policy version must be {expected_version}",
            "risk_policy_version_conflict",
            409,
        )
    previous_version = record.version
    timestamp = now_utc()
    result = session.execute(
        update(WorkspaceRiskPolicy)
        .where(
            WorkspaceRiskPolicy.workspace_id == workspace_id,
            WorkspaceRiskPolicy.version == previous_version,
        )
        .values(**payload.model_dump(), updated_at=timestamp)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise DomainError(
            "Risk policy was updated by another request",
            "risk_policy_version_conflict",
            409,
        )
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="risk_policy.updated",
        resource_type="risk_policy",
        resource_id=workspace_id,
        request_id=request_id,
        metadata={"version": payload.version},
    )
    session.commit()
    session.expire(record)
    return _risk_policy_response(record)


def _source_is_provider_reserved(source: str) -> bool:
    normalized = source.strip().lower()
    return any(
        normalized == namespace
        or any(
            normalized.startswith(f"{namespace}{separator}")
            for separator in (".", ":", "/", "-", "_")
        )
        for namespace in RESERVED_PROVIDER_SOURCE_NAMESPACES
    )


def _canonical_timestamp(value: datetime) -> str:
    normalized = (
        value.replace(tzinfo=UTC)
        if value.tzinfo is None
        else value.astimezone(UTC)
    )
    return normalized.isoformat(timespec="microseconds")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _event_material(
    *,
    repository_id: str | None,
    service_id: str | None,
    incident_id: str | None,
    event_type: str,
    occurred_at: datetime,
    severity: str,
    summary: str,
    attributes: dict[str, object],
    provenance: dict[str, object],
) -> dict[str, object]:
    normalized_provenance = dict(provenance)
    ingestion = normalized_provenance.pop("_ingestion", {})
    if not isinstance(ingestion, dict):
        ingestion = {}
    return {
        "repository_id": repository_id,
        "service_id": service_id,
        "incident_id": incident_id,
        "event_type": event_type.strip(),
        "occurred_at": _canonical_timestamp(occurred_at),
        "severity": severity,
        "summary": summary.strip(),
        "attributes": _canonical_json(attributes),
        "provenance": _canonical_json(normalized_provenance),
        "origin_channel": ingestion.get("channel"),
        "origin_actor_user_id": ingestion.get("actor_user_id"),
    }


def _stored_event_material(record: OperationalEvent) -> dict[str, object]:
    return _event_material(
        repository_id=record.repository_id,
        service_id=record.service_id,
        incident_id=record.incident_id,
        event_type=record.event_type,
        occurred_at=record.occurred_at,
        severity=record.severity,
        summary=record.summary,
        attributes=record.attributes,
        provenance=record.provenance,
    )


def _effective_event_repository_id(
    session: Session,
    workspace_id: str,
    payload: OperationalEventCreate,
) -> str | None:
    explicit_repository = _repository_for_workspace(
        session, workspace_id, payload.repository_id
    )
    service: ServiceCatalogEntry | None = None
    if payload.service_id is not None:
        service = _service_for_workspace(
            session, workspace_id, payload.service_id
        )
    incident: IncidentRecord | None = None
    if payload.incident_id is not None:
        incident = session.scalar(
            select(IncidentRecord).where(
                IncidentRecord.id == payload.incident_id,
                IncidentRecord.workspace_id == workspace_id,
            )
        )
        if incident is None:
            raise DomainError(
                "Incident not found", "incident_not_found", 404
            )

    repository_ids = {
        repository_id
        for repository_id in (
            explicit_repository.id
            if explicit_repository is not None
            else None,
            service.repository_id if service is not None else None,
            incident.repository_id if incident is not None else None,
        )
        if repository_id is not None
    }
    if len(repository_ids) > 1:
        raise DomainError(
            "Repository, service, and incident scopes do not match",
            "operational_event_scope_mismatch",
            422,
        )
    effective_repository_id = next(iter(repository_ids), None)
    if (
        effective_repository_id is not None
        and explicit_repository is None
    ):
        _repository_for_workspace(
            session, workspace_id, effective_repository_id
        )
    return effective_repository_id


def _record_normalized_operational_event(
    session: Session,
    workspace_id: str,
    payload: OperationalEventCreate,
    *,
    request_id: str,
    actor_user_id: str | None,
    provenance: dict[str, object],
) -> OperationalEventResponse:
    source = payload.source.strip().lower()
    effective_repository_id = _effective_event_repository_id(
        session, workspace_id, payload
    )
    expected_material = _event_material(
        repository_id=effective_repository_id,
        service_id=payload.service_id,
        incident_id=payload.incident_id,
        event_type=payload.event_type,
        occurred_at=payload.occurred_at,
        severity=payload.severity,
        summary=payload.summary,
        attributes=payload.attributes,
        provenance=provenance,
    )
    existing = session.scalar(
        select(OperationalEvent).where(
            OperationalEvent.workspace_id == workspace_id,
            OperationalEvent.source == source,
            OperationalEvent.provider_event_id == payload.provider_event_id,
        )
    )
    if existing is not None:
        if _stored_event_material(existing) != expected_material:
            raise DomainError(
                "Provider event ID was already used with different event data",
                "operational_event_idempotency_conflict",
                409,
            )
        return _event_response(existing)

    record = OperationalEvent(
        id=new_id(),
        provider_event_id=payload.provider_event_id,
        workspace_id=workspace_id,
        repository_id=effective_repository_id,
        service_id=payload.service_id,
        incident_id=payload.incident_id,
        source=source,
        event_type=payload.event_type.strip(),
        occurred_at=payload.occurred_at.astimezone(UTC),
        severity=payload.severity,
        summary=payload.summary.strip(),
        attributes=payload.attributes,
        provenance=provenance,
        ingestion_status=(
            "correlated" if payload.incident_id is not None else "accepted"
        ),
        ingested_at=now_utc(),
    )
    session.add(record)
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="operational_event.ingested",
        resource_type="operational_event",
        resource_id=record.id,
        request_id=request_id,
        metadata={
            "source": source,
            "event_type": record.event_type,
            "ingestion_status": record.ingestion_status,
        },
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(OperationalEvent).where(
                OperationalEvent.workspace_id == workspace_id,
                OperationalEvent.source == source,
                OperationalEvent.provider_event_id
                == payload.provider_event_id,
            )
        )
        if existing is None:
            raise
        if _stored_event_material(existing) != expected_material:
            raise DomainError(
                "Provider event ID was concurrently used with different event data",
                "operational_event_idempotency_conflict",
                409,
            )
        return _event_response(existing)
    return _event_response(record)


def record_trusted_operational_event(
    session: Session,
    workspace_id: str,
    payload: OperationalEventCreate,
    *,
    request_id: str,
) -> OperationalEventResponse:
    """Persist an event from a trusted internal provider adapter.

    This function is intentionally separate from the member-authenticated API
    boundary. Callers must first authenticate and tenant-map the provider event.
    """
    return _record_normalized_operational_event(
        session,
        workspace_id,
        payload,
        request_id=request_id,
        actor_user_id=None,
        provenance={
            **payload.provenance,
            "_ingestion": {
                "channel": "trusted_internal",
                "actor_user_id": None,
                "request_id": request_id,
            },
        },
    )


def record_operational_event(
    session: Session,
    workspace_id: str,
    payload: OperationalEventCreate,
    *,
    request_id: str,
) -> OperationalEventResponse:
    """Backward-compatible trusted provider adapter entry point."""
    return record_trusted_operational_event(
        session,
        workspace_id,
        payload,
        request_id=request_id,
    )


def ingest_operational_event(
    session: Session,
    user: User,
    workspace_id: str,
    payload: ManualOperationalEventCreate,
    request_id: str,
) -> OperationalEventResponse:
    membership_for(session, user, workspace_id, "responder")
    source = payload.source.strip().lower()
    if _source_is_provider_reserved(source):
        raise DomainError(
            "This event source is reserved for an authenticated provider adapter",
            "operational_event_source_reserved",
            422,
        )
    return _record_normalized_operational_event(
        session,
        workspace_id,
        payload,
        request_id=request_id,
        actor_user_id=user.id,
        provenance={
            "origin": "authenticated_member",
            "_ingestion": {
                "channel": "member_api",
                "actor_user_id": user.id,
                "request_id": request_id,
            },
        },
    )


def list_operational_events(
    session: Session,
    user: User,
    workspace_id: str,
    *,
    source: str | None,
    event_type: str | None,
    severity: str | None,
    repository_id: str | None,
    service_id: str | None,
    ingestion_status: str | None,
    occurred_after: datetime | None,
    occurred_before: datetime | None,
    limit: int,
) -> list[OperationalEventResponse]:
    membership_for(session, user, workspace_id)
    statement = select(OperationalEvent).where(
        OperationalEvent.workspace_id == workspace_id
    )
    filters = (
        (OperationalEvent.source, source.strip().lower() if source else None),
        (OperationalEvent.event_type, event_type),
        (OperationalEvent.severity, severity),
        (OperationalEvent.repository_id, repository_id),
        (OperationalEvent.service_id, service_id),
        (OperationalEvent.ingestion_status, ingestion_status),
    )
    for column, value in filters:
        if value is not None:
            statement = statement.where(column == value)
    if occurred_after is not None:
        statement = statement.where(
            OperationalEvent.occurred_at >= occurred_after
        )
    if occurred_before is not None:
        statement = statement.where(
            OperationalEvent.occurred_at <= occurred_before
        )
    records = session.scalars(
        statement.order_by(
            OperationalEvent.occurred_at.desc(),
            OperationalEvent.id.desc(),
        ).limit(limit)
    ).all()
    return [_event_response(item) for item in records]


def _normalize_incident_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in INCIDENT_STATUS_ORDER:
        raise DomainError(
            "Incident has an unsupported lifecycle status",
            "invalid_incident_status",
            409,
        )
    return normalized


def _normalize_incident_severity(value: str) -> str:
    normalized = value.strip().lower().replace("-", "")
    if normalized not in {"sev1", "sev2", "sev3", "sev4"}:
        raise DomainError(
            "Incident has an unsupported severity",
            "invalid_incident_severity",
            409,
        )
    return normalized


def _stored_incident_severity(value: str) -> str:
    return f"SEV-{value[-1]}"


def _timeline_entry(
    *,
    event_type: str,
    title: str,
    detail: str,
    actor_user_id: str,
    timestamp: datetime,
) -> dict[str, str | None]:
    return {
        "id": f"timeline-{uuid4()}",
        "timestamp": timestamp.isoformat(),
        "type": event_type,
        "title": title,
        "detail": detail,
        "service_id": None,
        "actor_user_id": actor_user_id,
    }


def _create_workspace_notifications(
    session: Session,
    *,
    workspace_id: str,
    kind: str,
    title: str,
    message: str,
    incident_id: str,
    timestamp: datetime,
) -> None:
    member_ids = session.scalars(
        select(WorkspaceMembership.user_id).where(
            WorkspaceMembership.workspace_id == workspace_id
        )
    ).all()
    for user_id in member_ids:
        session.add(
            Notification(
                id=new_id(),
                workspace_id=workspace_id,
                user_id=user_id,
                kind=kind,
                title=title[:240],
                message=message[:1_000],
                resource_type="incident",
                resource_id=incident_id,
                read_at=None,
                created_at=timestamp,
            )
        )


def _lifecycle_response(
    record: IncidentRecord,
) -> IncidentLifecycleResponse:
    return IncidentLifecycleResponse(
        incident_id=record.id,
        workspace_id=record.workspace_id,
        status=_normalize_incident_status(record.status),
        severity=_normalize_incident_severity(record.severity),
        assignee_user_id=record.assignee_user_id,
        resolved_at=record.resolved_at,
        timeline=[
            TimelineEvent.model_validate(item)
            for item in (record.timeline or [])
        ],
    )


def update_incident_lifecycle(
    session: Session,
    user: User,
    workspace_id: str,
    incident_id: str,
    payload: IncidentLifecycleUpdate,
    request_id: str,
) -> IncidentLifecycleResponse:
    membership_for(session, user, workspace_id, "responder")
    record = session.scalar(
        select(IncidentRecord)
        .where(
            IncidentRecord.id == incident_id,
            IncidentRecord.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if record is None:
        raise DomainError("Incident not found", "incident_not_found", 404)
    current_status = _normalize_incident_status(record.status)
    if current_status == "resolved":
        raise DomainError(
            "Resolved incident lifecycle records are immutable",
            "incident_already_resolved",
            409,
        )

    changes: list[str] = []
    if "status" in payload.model_fields_set and payload.status is not None:
        if (
            INCIDENT_STATUS_ORDER[payload.status]
            < INCIDENT_STATUS_ORDER[current_status]
        ):
            raise DomainError(
                "Incident lifecycle cannot move backwards",
                "invalid_incident_transition",
                409,
            )
        if payload.status != current_status:
            changes.append(f"status {current_status} → {payload.status}")
            record.status = payload.status
            if payload.status == "resolved":
                record.resolved_at = now_utc()

    if "assignee_user_id" in payload.model_fields_set:
        if payload.assignee_user_id is not None:
            assignee = session.scalar(
                select(WorkspaceMembership)
                .join(User, User.id == WorkspaceMembership.user_id)
                .where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceMembership.user_id == payload.assignee_user_id,
                    User.is_active.is_(True),
                )
            )
            if assignee is None:
                raise DomainError(
                    "Assignee must be a member of this workspace",
                    "invalid_incident_assignee",
                    422,
                )
        if record.assignee_user_id != payload.assignee_user_id:
            changes.append(
                "assignee updated"
                if payload.assignee_user_id is not None
                else "assignee cleared"
            )
            record.assignee_user_id = payload.assignee_user_id

    if "severity" in payload.model_fields_set and payload.severity is not None:
        current_severity = _normalize_incident_severity(record.severity)
        if current_severity != payload.severity:
            changes.append(
                f"severity {current_severity} → {payload.severity}"
            )
            record.severity = _stored_incident_severity(payload.severity)

    if not changes:
        return _lifecycle_response(record)

    timestamp = now_utc()
    detail = "; ".join(changes)
    entry = _timeline_entry(
        event_type="incident_lifecycle",
        title="Incident lifecycle updated",
        detail=detail,
        actor_user_id=user.id,
        timestamp=timestamp,
    )
    record.timeline = [*(record.timeline or []), entry]
    _create_workspace_notifications(
        session,
        workspace_id=workspace_id,
        kind="incident_lifecycle",
        title=f"Incident updated: {record.title}",
        message=detail,
        incident_id=record.id,
        timestamp=timestamp,
    )
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="incident.lifecycle_updated",
        resource_type="incident",
        resource_id=record.id,
        request_id=request_id,
        metadata={"changes": changes},
    )
    session.commit()
    return _lifecycle_response(record)


def add_incident_note(
    session: Session,
    user: User,
    workspace_id: str,
    incident_id: str,
    payload: IncidentNoteCreate,
    request_id: str,
) -> TimelineEvent:
    membership_for(session, user, workspace_id, "responder")
    record = session.scalar(
        select(IncidentRecord)
        .where(
            IncidentRecord.id == incident_id,
            IncidentRecord.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if record is None:
        raise DomainError("Incident not found", "incident_not_found", 404)
    timestamp = now_utc()
    entry = _timeline_entry(
        event_type="incident_note",
        title="Investigation note",
        detail=payload.note.strip(),
        actor_user_id=user.id,
        timestamp=timestamp,
    )
    record.timeline = [*(record.timeline or []), entry]
    _create_workspace_notifications(
        session,
        workspace_id=workspace_id,
        kind="incident_note",
        title=f"New note: {record.title}",
        message=payload.note.strip(),
        incident_id=record.id,
        timestamp=timestamp,
    )
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="incident.note_added",
        resource_type="incident",
        resource_id=record.id,
        request_id=request_id,
    )
    session.commit()
    return TimelineEvent.model_validate(entry)


def list_notifications(
    session: Session,
    user: User,
    *,
    workspace_id: str | None,
    unread_only: bool,
    limit: int,
) -> list[NotificationResponse]:
    if workspace_id is not None:
        membership_for(session, user, workspace_id)
    statement = select(Notification).where(Notification.user_id == user.id)
    if workspace_id is not None:
        statement = statement.where(
            Notification.workspace_id == workspace_id
        )
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    records = session.scalars(
        statement.order_by(
            Notification.created_at.desc(), Notification.id.desc()
        ).limit(limit)
    ).all()
    return [_notification_response(item) for item in records]


def mark_notification_read(
    session: Session, user: User, notification_id: str
) -> NotificationResponse:
    record = session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    if record is None:
        raise DomainError(
            "Notification not found", "notification_not_found", 404
        )
    if record.read_at is None:
        record.read_at = now_utc()
        session.commit()
    return _notification_response(record)
