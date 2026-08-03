"""Tenant-authorized operational controls for failed background jobs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import DomainError
from .job_models import BackgroundJob
from .job_queue import JobStateError, replay_dead_letter_job
from .models import User
from .operations_schemas import BackgroundJobSummary
from .workspace_services import audit, membership_for


def list_jobs_requiring_attention(
    session: Session,
    user: User,
    workspace_id: str,
    *,
    limit: int,
) -> list[BackgroundJobSummary]:
    membership_for(session, user, workspace_id, "responder")
    rows = session.scalars(
        select(BackgroundJob)
        .where(
            BackgroundJob.workspace_id == workspace_id,
            BackgroundJob.status.in_(("failed", "dead_letter")),
        )
        .order_by(BackgroundJob.updated_at.desc(), BackgroundJob.id)
        .limit(limit)
    ).all()
    return [BackgroundJobSummary.model_validate(row) for row in rows]


def replay_failed_job(
    session: Session,
    user: User,
    workspace_id: str,
    job_id: str,
    request_id: str,
) -> BackgroundJobSummary:
    membership_for(session, user, workspace_id, "admin")
    job = session.scalar(
        select(BackgroundJob).where(
            BackgroundJob.id == job_id,
            BackgroundJob.workspace_id == workspace_id,
        )
    )
    if job is None:
        raise DomainError("Background job not found", "job_not_found", 404)
    previous_status = job.status
    try:
        replay_dead_letter_job(session, job.id, commit=False)
    except JobStateError as error:
        raise DomainError(
            "Background job is not replayable", "job_not_replayable", 409
        ) from error
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="background_job.replayed",
        resource_type="background_job",
        resource_id=job.id,
        request_id=request_id,
        metadata={"previous_status": previous_status},
    )
    session.commit()
    return BackgroundJobSummary.model_validate(job)
