"""Durable, provider-agnostic background job queue primitives.

This module owns persistence and delivery semantics only.  Applications must
register safe handlers in a separate worker process; no handler is inferred and
no external side effect is performed here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Any, Callable, TypeAlias
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .job_models import BackgroundJob


MAX_ERROR_LENGTH = 4_000
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_SECONDS = 30
DEFAULT_MAX_BACKOFF_SECONDS = 3_600
_SENSITIVE_PAYLOAD_KEY = re.compile(
    r"(?:^|_)(?:token|secret|password|passwd|private_key|api_key|authorization|credential)(?:$|_)",
    re.IGNORECASE,
)


class JobNotFound(KeyError):
    """Raised when a queue operation references an unknown job."""


class JobStateError(RuntimeError):
    """Raised when a job transition is not valid for its current state."""


JobHandler: TypeAlias = Callable[
    [Mapping[str, Any]], Mapping[str, Any] | None
]


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _job_or_raise(session: Session, job_id: str) -> BackgroundJob:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        raise JobNotFound(job_id)
    return job


def _validate_attempts(max_attempts: int) -> None:
    if not 1 <= max_attempts <= 100:
        raise ValueError("max_attempts must be between 1 and 100")


def _validate_payload(value: Any, *, path: str = "payload") -> None:
    """Reject secrets and non-JSON values before they enter the outbox."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            normalized_key = re.sub(r"(?<!^)([A-Z])", r"_\1", key_text)
            if _SENSITIVE_PAYLOAD_KEY.search(normalized_key):
                raise ValueError(
                    f"{path}.{key_text} looks like a credential; store references, not secrets"
                )
            _validate_payload(nested, path=f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_payload(nested, path=f"{path}[{index}]")
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must contain JSON-compatible values") from exc


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    payload: Mapping[str, Any],
    idempotency_key: str | None = None,
    workspace_id: str | None = None,
    request_id: str | None = None,
    available_at: datetime | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> BackgroundJob:
    """Persist a queued job and return the existing row for duplicate intents.

    ``idempotency_key`` is globally unique.  Reusing one key is safe and
    returns the original job, while changing the job type or payload is
    intentionally ignored so retries cannot mutate an already accepted intent.
    """

    normalized_type = job_type.strip()
    if not normalized_type or len(normalized_type) > 120:
        raise ValueError("job_type must contain 1 to 120 characters")
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 160:
            raise ValueError("idempotency_key must contain 1 to 160 characters")
    _validate_attempts(max_attempts)
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a JSON object")
    _validate_payload(payload)

    if idempotency_key:
        existing = session.scalar(
            select(BackgroundJob).where(
                BackgroundJob.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing

    now = _now(None)
    job = BackgroundJob(
        id=str(uuid4()),
        job_type=normalized_type,
        workspace_id=workspace_id,
        payload=dict(payload),
        idempotency_key=idempotency_key,
        status="queued",
        attempts=0,
        max_attempts=max_attempts,
        available_at=available_at or now,
        locked_at=None,
        locked_by=None,
        last_error=None,
        result=None,
        request_id=request_id,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent producer may have won the unique idempotency race.
        session.rollback()
        if idempotency_key:
            existing = session.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                return existing
        raise
    return job


def requeue_expired_jobs(
    session: Session,
    *,
    lease_timeout: timedelta = timedelta(minutes=5),
    now: datetime | None = None,
) -> int:
    """Return abandoned running jobs to the queue, or dead-letter exhausted ones."""

    timestamp = _now(now)
    cutoff = timestamp - lease_timeout
    jobs = session.scalars(
        select(BackgroundJob).where(
            BackgroundJob.status == "running",
            BackgroundJob.locked_at.is_not(None),
            BackgroundJob.locked_at < cutoff,
        )
    ).all()
    for job in jobs:
        job.locked_at = None
        job.locked_by = None
        job.updated_at = timestamp
        job.last_error = "worker lease expired"
        if job.attempts >= job.max_attempts:
            job.status = "dead_letter"
            job.completed_at = timestamp
        else:
            job.status = "queued"
            job.available_at = timestamp
    if jobs:
        session.commit()
    return len(jobs)


def claim_next_job(
    session: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> BackgroundJob | None:
    """Atomically claim the oldest ready job for a worker.

    The compare-and-set update protects SQLite deployments where row-level
    ``SKIP LOCKED`` is unavailable, while PostgreSQL can still use the indexed
    ready query efficiently.
    """

    normalized_worker = worker_id.strip()
    if not normalized_worker or len(normalized_worker) > 160:
        raise ValueError("worker_id must contain 1 to 160 characters")
    timestamp = _now(now)
    candidates = session.scalars(
        select(BackgroundJob)
        .where(
            BackgroundJob.status == "queued",
            BackgroundJob.available_at <= timestamp,
        )
        .order_by(BackgroundJob.available_at, BackgroundJob.created_at)
        .limit(20)
    ).all()
    for candidate in candidates:
        result = session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == candidate.id,
                BackgroundJob.status == "queued",
                BackgroundJob.available_at <= timestamp,
            )
            .values(
                status="running",
                attempts=BackgroundJob.attempts + 1,
                locked_at=timestamp,
                locked_by=normalized_worker,
                updated_at=timestamp,
            )
        )
        if result.rowcount:
            session.commit()
            return session.get(BackgroundJob, candidate.id)
    return None


def complete_job(
    session: Session,
    job_id: str,
    *,
    result: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> BackgroundJob:
    """Mark a claimed job successful and persist a non-sensitive result."""

    job = _job_or_raise(session, job_id)
    if job.status != "running":
        raise JobStateError(f"job {job_id} is not running")
    if result is not None:
        _validate_payload(result, path="result")
    timestamp = _now(now)
    job.status = "succeeded"
    job.result = dict(result) if result is not None else None
    job.locked_at = None
    job.locked_by = None
    job.updated_at = timestamp
    job.completed_at = timestamp
    session.commit()
    return job


def fail_job(
    session: Session,
    job_id: str,
    *,
    error: str,
    retryable: bool = True,
    now: datetime | None = None,
    backoff_seconds: int = DEFAULT_BACKOFF_SECONDS,
    max_backoff_seconds: int = DEFAULT_MAX_BACKOFF_SECONDS,
) -> BackgroundJob:
    """Record a failure and schedule a bounded retry or dead-letter the job."""

    if backoff_seconds < 0 or max_backoff_seconds < 0:
        raise ValueError("backoff values cannot be negative")
    if max_backoff_seconds < backoff_seconds:
        raise ValueError("max_backoff_seconds must be >= backoff_seconds")
    job = _job_or_raise(session, job_id)
    if job.status != "running":
        raise JobStateError(f"job {job_id} is not running")
    timestamp = _now(now)
    job.last_error = error.strip()[:MAX_ERROR_LENGTH] or "job failed"
    job.locked_at = None
    job.locked_by = None
    job.updated_at = timestamp
    if retryable and job.attempts < job.max_attempts:
        delay = min(
            backoff_seconds * (2 ** max(job.attempts - 1, 0)),
            max_backoff_seconds,
        )
        job.status = "queued"
        job.available_at = timestamp + timedelta(seconds=delay)
    elif retryable:
        job.status = "dead_letter"
        job.completed_at = timestamp
    else:
        job.status = "failed"
        job.completed_at = timestamp
    session.commit()
    return job


def replay_dead_letter_job(
    session: Session,
    job_id: str,
    *,
    available_at: datetime | None = None,
    now: datetime | None = None,
) -> BackgroundJob:
    """Explicitly requeue a dead-letter job with a fresh retry budget."""

    job = _job_or_raise(session, job_id)
    if job.status != "dead_letter":
        raise JobStateError(f"job {job_id} is not dead-lettered")
    timestamp = _now(now)
    job.status = "queued"
    job.attempts = 0
    job.available_at = available_at or timestamp
    job.locked_at = None
    job.locked_by = None
    job.last_error = None
    job.result = None
    job.updated_at = timestamp
    job.completed_at = None
    session.commit()
    return job


def run_one_job(
    session: Session,
    *,
    worker_id: str,
    handlers: Mapping[str, JobHandler],
    now: datetime | None = None,
) -> BackgroundJob | None:
    """Run one explicitly registered handler and fail closed otherwise.

    This helper is intentionally not wired into the web process.  A deployment
    may call it from a separately supervised worker with a small allow-list of
    handlers.  Unknown job types become permanent failures and never execute a
    guessed or autonomous action.
    """

    job = claim_next_job(session, worker_id=worker_id, now=now)
    if job is None:
        return None
    handler = handlers.get(job.job_type)
    if handler is None or not callable(handler):
        return fail_job(
            session,
            job.id,
            error=f"no handler registered for job type {job.job_type}",
            retryable=False,
            now=now,
        )
    try:
        output = handler(job.payload)
    except Exception as exc:  # handlers decide side effects; queue records failure
        return fail_job(session, job.id, error=str(exc), retryable=True, now=now)
    return complete_job(session, job.id, result=output, now=now)
