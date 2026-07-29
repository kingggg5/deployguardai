from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from .auth.dependencies import get_current_user, get_session
from .models import User
from .operations_schemas import (
    EventSeverity,
    IncidentLifecycleResponse,
    IncidentLifecycleUpdate,
    IncidentNoteCreate,
    IngestionStatus,
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
from .operations_services import (
    add_incident_note,
    create_service,
    get_risk_policy,
    get_service,
    ingest_operational_event,
    list_notifications,
    list_operational_events,
    list_services,
    mark_notification_read,
    update_incident_lifecycle,
    update_risk_policy,
    update_service,
)
from .schemas import TimelineEvent
from .tenant import TenantScope, require_responder_scope
from .workspace_api import request_id


router = APIRouter(prefix="/api/v1")


@router.get(
    "/workspaces/{workspace_id}/services",
    response_model=list[ServiceResponse],
)
def services(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[ServiceResponse]:
    return list_services(session, user, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/services",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
def service_create(
    workspace_id: str,
    payload: ServiceCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ServiceResponse:
    return create_service(
        session, user, workspace_id, payload, request_id(request)
    )


@router.get("/services/{service_id}", response_model=ServiceResponse)
def service(
    service_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ServiceResponse:
    return get_service(session, user, service_id)


@router.patch("/services/{service_id}", response_model=ServiceResponse)
def service_patch(
    service_id: str,
    payload: ServiceUpdate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ServiceResponse:
    return update_service(
        session, user, service_id, payload, request_id(request)
    )


@router.get(
    "/workspaces/{workspace_id}/risk-policy",
    response_model=RiskPolicyResponse,
)
def risk_policy(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> RiskPolicyResponse:
    return get_risk_policy(session, user, workspace_id)


@router.put(
    "/workspaces/{workspace_id}/risk-policy",
    response_model=RiskPolicyResponse,
)
def risk_policy_update(
    workspace_id: str,
    payload: RiskPolicyUpdate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> RiskPolicyResponse:
    return update_risk_policy(
        session, user, workspace_id, payload, request_id(request)
    )


@router.post(
    "/workspaces/{workspace_id}/events",
    response_model=OperationalEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def operational_event_ingest(
    workspace_id: str,
    payload: ManualOperationalEventCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> OperationalEventResponse:
    return ingest_operational_event(
        session,
        user,
        workspace_id,
        payload,
        request_id(request),
    )


@router.get(
    "/workspaces/{workspace_id}/events",
    response_model=list[OperationalEventResponse],
)
def operational_events(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    source: str | None = Query(default=None, min_length=1, max_length=100),
    event_type: str | None = Query(
        default=None, min_length=1, max_length=100
    ),
    severity: EventSeverity | None = None,
    repository_id: str | None = Query(default=None, max_length=36),
    service_id: str | None = Query(default=None, max_length=36),
    ingestion_status: IngestionStatus | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OperationalEventResponse]:
    return list_operational_events(
        session,
        user,
        workspace_id,
        source=source,
        event_type=event_type,
        severity=severity,
        repository_id=repository_id,
        service_id=service_id,
        ingestion_status=ingestion_status,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        limit=limit,
    )


@router.patch(
    "/incidents/{incident_id}/lifecycle",
    response_model=IncidentLifecycleResponse,
)
def incident_lifecycle_update(
    incident_id: str,
    payload: IncidentLifecycleUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    scope: Annotated[TenantScope, Depends(require_responder_scope)],
) -> IncidentLifecycleResponse:
    return update_incident_lifecycle(
        session,
        scope.user,
        scope.workspace_id,
        incident_id,
        payload,
        request_id(request),
    )


@router.post(
    "/incidents/{incident_id}/notes",
    response_model=TimelineEvent,
    status_code=status.HTTP_201_CREATED,
)
def incident_note_create(
    incident_id: str,
    payload: IncidentNoteCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    scope: Annotated[TenantScope, Depends(require_responder_scope)],
) -> TimelineEvent:
    return add_incident_note(
        session,
        scope.user,
        scope.workspace_id,
        incident_id,
        payload,
        request_id(request),
    )


@router.get("/notifications", response_model=list[NotificationResponse])
def notifications(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    workspace_id: str | None = Query(default=None, max_length=36),
    unread_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[NotificationResponse]:
    return list_notifications(
        session,
        user,
        workspace_id=workspace_id,
        unread_only=unread_only,
        limit=limit,
    )


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
def notification_read(
    notification_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> NotificationResponse:
    return mark_notification_read(session, user, notification_id)
