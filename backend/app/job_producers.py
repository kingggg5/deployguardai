"""Transactional producers for explicit background-job contracts."""

from sqlalchemy.orm import Session

from .config import Settings
from .job_contracts import (
    GITHUB_CHECK_PUBLISH_JOB,
    GitHubCheckPublishPayload,
    INVITATION_EMAIL_DELIVER_JOB,
    InvitationEmailDeliverPayload,
    validated_trace_context,
)
from .job_models import BackgroundJob
from .job_queue import enqueue_job
from .models import ChangeRecord, Invitation, Repository
from .provider_models import ProviderConnection


def enqueue_github_check_publication(
    session: Session,
    *,
    connection: ProviderConnection,
    repository: Repository,
    change: ChangeRecord,
    request_id: str,
    settings: Settings,
    traceparent: str | None = None,
    tracestate: str | None = None,
    commit: bool = False,
) -> BackgroundJob | None:
    """Persist a Check-publication intent without performing provider I/O.

    Webhook ingestion uses ``commit=False`` and commits this row together with
    its delivery status.  The manual responder endpoint intentionally remains
    synchronous because it is an explicit, user-initiated operation.
    """

    if (
        not settings.github_checks_enabled
        or connection.connection_state != "connected"
        or str((connection.permissions or {}).get("checks", "")).lower()
        != "write"
    ):
        return None
    if (
        repository.workspace_id != connection.workspace_id
        or change.workspace_id != connection.workspace_id
        or change.repository_id != repository.id
        or repository.provider != "github"
        or not repository.selected
        or change.data_mode != "connected"
    ):
        return None

    contract = GitHubCheckPublishPayload(
        connection_id=connection.id,
        repository_id=repository.id,
        change_id=change.id,
        trace_context=validated_trace_context(traceparent, tracestate),
    )
    return enqueue_job(
        session,
        job_type=GITHUB_CHECK_PUBLISH_JOB,
        payload=contract.model_dump(mode="json", exclude_none=True),
        idempotency_key=f"github-check:{repository.id}:{change.id}",
        workspace_id=connection.workspace_id,
        request_id=request_id,
        max_attempts=5,
        commit=commit,
    )


def enqueue_invitation_email_delivery(
    session: Session,
    *,
    invitation: Invitation,
    request_id: str,
    commit: bool = False,
) -> BackgroundJob:
    """Queue one SMTP invitation delivery without serializing the claim token."""

    contract = InvitationEmailDeliverPayload(invitation_id=invitation.id)
    return enqueue_job(
        session,
        job_type=INVITATION_EMAIL_DELIVER_JOB,
        payload=contract.model_dump(mode="json"),
        idempotency_key=f"invitation-email:{invitation.id}",
        workspace_id=invitation.workspace_id,
        request_id=request_id,
        # SMTP has no idempotency key.  Once an attempt reaches the provider,
        # the handler records an uncertain result instead of retrying blindly.
        max_attempts=1,
        commit=commit,
    )
