"""Tenant-scoped, allow-listed notification outbox producers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .errors import DomainError
from .job_producers import enqueue_operational_notification_delivery
from .job_models import BackgroundJob
from .operations_models import OperationalEvent
from .operations_schemas import (
    NotificationDeliveryResponse,
    NotificationProviderRequest,
)
from .models import User
from .workspace_services import audit, membership_for


def queue_notification_delivery(
    session: Session,
    user: User,
    workspace_id: str,
    payload: NotificationProviderRequest,
    *,
    settings: Settings,
    request_id: str,
) -> NotificationDeliveryResponse:
    """Queue a notification for a fixed deployment-owned provider.

    The API accepts an existing operational event ID instead of arbitrary
    message text or a destination URL. The supervised worker owns the only
    provider I/O path and reads destination credentials from Settings.
    """

    membership_for(session, user, workspace_id, "responder")
    if not settings.notification_provider_configured(payload.provider):
        raise DomainError(
            f"{payload.provider} notification provider is not configured",
            "notification_provider_not_configured",
            503,
        )
    event = session.scalar(
        select(OperationalEvent).where(
            OperationalEvent.id == payload.event_id,
            OperationalEvent.workspace_id == workspace_id,
        )
    )
    if event is None:
        raise DomainError(
            "Operational event not found",
            "operational_event_not_found",
            404,
        )
    job = enqueue_operational_notification_delivery(
        session,
        workspace_id=workspace_id,
        provider=payload.provider,
        event_id=event.id,
        request_id=request_id,
        commit=False,
    )
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="notification.delivery.queued",
        resource_type="operational_event",
        resource_id=event.id,
        request_id=request_id,
        metadata={"provider": payload.provider, "job_id": job.id},
    )
    session.commit()
    return NotificationDeliveryResponse(
        job_id=job.id,
        provider=payload.provider,
        event_id=event.id,
        status=job.status,
        created_at=job.created_at,
    )
