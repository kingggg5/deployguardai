from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.database import Database
from app.job_queue import (
    JobContext,
    JobStateError,
    PermanentJobError,
    claim_next_job,
    complete_job,
    enqueue_job,
    fail_job,
    replay_dead_letter_job,
    requeue_expired_jobs,
    run_one_job,
)


@pytest.fixture
def queue_session(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}")
    database.migrate(allow_legacy_bootstrap=True)
    session = database.session_factory()
    try:
        yield session
    finally:
        session.close()
        database.dispose()


def test_enqueue_is_idempotent_and_rejects_credentials(queue_session) -> None:
    first = enqueue_job(
        queue_session,
        job_type="telemetry.ingest",
        payload={"event_id": "evt-1"},
        idempotency_key="evt-1",
    )
    duplicate = enqueue_job(
        queue_session,
        job_type="telemetry.ingest",
        payload={"event_id": "different"},
        idempotency_key="evt-1",
    )
    assert duplicate.id == first.id
    with pytest.raises(ValueError, match="credential"):
        enqueue_job(
            queue_session,
            job_type="provider.sync",
            payload={"access_token": "never-store-this"},
        )


def test_enqueue_can_join_the_producer_transaction(queue_session) -> None:
    job = enqueue_job(
        queue_session,
        job_type="safe.noop",
        payload={"value": 1},
        idempotency_key="transactional-intent",
        commit=False,
    )
    assert queue_session.get(type(job), job.id) is not None

    queue_session.rollback()
    assert queue_session.get(type(job), job.id) is None


def test_handler_receives_correlation_context_and_can_fail_permanently(
    queue_session,
) -> None:
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    enqueue_job(
        queue_session,
        job_type="safe.validate",
        payload={"value": 1},
        request_id="request-123",
        available_at=now,
    )
    observed: list[JobContext] = []

    def reject(_payload, context: JobContext):
        observed.append(context)
        raise PermanentJobError("invalid immutable reference")

    failed = run_one_job(
        queue_session,
        worker_id="worker-a",
        handlers={"safe.validate": reject},
        now=now,
    )
    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempts == 1
    assert observed[0].request_id == "request-123"
    assert observed[0].attempt == 1
    replayed = replay_dead_letter_job(queue_session, failed.id, now=now)
    assert replayed.status == "queued"
    assert replayed.attempts == 0


def test_claim_complete_and_unknown_handler_fail_closed(queue_session) -> None:
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    job = enqueue_job(
        queue_session,
        job_type="safe.noop",
        payload={"value": 1},
        available_at=now,
    )
    claimed = claim_next_job(queue_session, worker_id="worker-a", now=now)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    completed = complete_job(queue_session, claimed.id, result={"ok": True}, now=now)
    assert completed.status == "succeeded"
    assert completed.result == {"ok": True}
    with pytest.raises(JobStateError):
        complete_job(queue_session, claimed.id, now=now)

    unknown = enqueue_job(
        queue_session,
        job_type="not.registered",
        payload={},
        available_at=now,
    )
    failed = run_one_job(
        queue_session,
        worker_id="worker-a",
        handlers={},
        now=now,
    )
    assert failed is not None
    assert failed.id == unknown.id
    assert failed.status == "failed"


def test_retry_backoff_dead_letter_and_explicit_replay(queue_session) -> None:
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    job = enqueue_job(
        queue_session,
        job_type="github.check.publish",
        payload={"publication_id": "pub-1"},
        max_attempts=2,
        available_at=now,
    )
    first = claim_next_job(queue_session, worker_id="worker-a", now=now)
    assert first is not None
    retry = fail_job(
        queue_session,
        first.id,
        error="provider timeout",
        now=now,
        backoff_seconds=10,
        max_backoff_seconds=60,
    )
    assert retry.status == "queued"
    assert retry.available_at == now + timedelta(seconds=10)
    second = claim_next_job(
        queue_session,
        worker_id="worker-a",
        now=now + timedelta(seconds=10),
    )
    assert second is not None
    dead = fail_job(
        queue_session,
        second.id,
        error="provider unavailable",
        now=now + timedelta(seconds=10),
    )
    assert dead.status == "dead_letter"
    replayed = replay_dead_letter_job(queue_session, dead.id, now=now)
    assert replayed.status == "queued"
    assert replayed.attempts == 0


def test_expired_worker_lease_is_requeued_or_dead_lettered(queue_session) -> None:
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    job = enqueue_job(
        queue_session,
        job_type="telemetry.ingest",
        payload={"event_id": "evt-2"},
        max_attempts=2,
        available_at=now,
    )
    claimed = claim_next_job(queue_session, worker_id="worker-a", now=now)
    assert claimed is not None
    moved = requeue_expired_jobs(
        queue_session,
        lease_timeout=timedelta(seconds=30),
        now=now + timedelta(seconds=31),
    )
    assert moved == 1
    assert queue_session.get(type(job), job.id).status == "queued"
