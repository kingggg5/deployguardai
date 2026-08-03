"""Separately supervised worker for the explicit DeployGuard job allowlist."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import timedelta
import json
import logging
import os
import signal
import socket
from threading import Event
from typing import Any

from pydantic import ValidationError
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from sqlalchemy.orm import Session

from . import provider_services
from .config import Settings
from .database import Database
from .errors import DomainError
from .job_contracts import GITHUB_CHECK_PUBLISH_JOB, GitHubCheckPublishPayload
from .job_queue import (
    JobContext,
    JobHandler,
    PermanentJobError,
    requeue_expired_jobs,
    run_one_job,
)
from .models import ChangeRecord, Repository
from .observability import (
    attach_trace_context,
    configure_tracing,
    detach_trace_context,
)
from .provider_models import ProviderConnection
from .rls import set_tenant_context


logger = logging.getLogger("deployguard.worker")


def github_check_publish_handler(
    session: Session,
    settings: Settings,
) -> JobHandler:
    """Build the one provider handler currently allowed by this worker."""

    def handle(
        raw_payload: Mapping[str, Any],
        context: JobContext,
    ) -> Mapping[str, Any]:
        try:
            payload = GitHubCheckPublishPayload.model_validate(raw_payload)
        except ValidationError as error:
            raise PermanentJobError(
                "github.check.publish payload failed contract validation"
            ) from error
        if not settings.github_checks_enabled:
            raise PermanentJobError("GitHub Check publishing is disabled")
        if context.workspace_id is None:
            raise PermanentJobError("GitHub Check job is missing workspace scope")
        set_tenant_context(session, context.workspace_id)

        connection = session.get(ProviderConnection, payload.connection_id)
        repository = session.get(Repository, payload.repository_id)
        change = session.get(ChangeRecord, payload.change_id)
        workspace_id = context.workspace_id
        if connection is None or repository is None or change is None:
            raise PermanentJobError(
                "GitHub Check references are missing or deleted"
            )
        if (
            connection.workspace_id != workspace_id
            or repository.workspace_id != workspace_id
            or change.workspace_id != workspace_id
            or change.repository_id != repository.id
            or repository.provider != "github"
            or change.data_mode != "connected"
        ):
            raise PermanentJobError(
                "GitHub Check references are invalid or cross-tenant"
            )
        if (
            connection.connection_state != "connected"
            or str((connection.permissions or {}).get("checks", "")).lower()
            != "write"
            or not repository.selected
        ):
            raise RuntimeError("github_check_provider_not_ready")

        try:
            response = provider_services._publish_github_change_check(
                session,
                connection=connection,
                repository=repository,
                change=change,
                actor_user_id=None,
                request_id=context.request_id or f"job:{context.job_id}",
                settings=settings,
            )
        except DomainError as error:
            if error.code in provider_services.GITHUB_CHECK_RETRYABLE_ERRORS:
                raise RuntimeError(error.code) from error
            raise PermanentJobError(error.code) from error
        return {
            "provider_check_id": response.provider_check_id,
            "change_id": response.change_id,
            "status": response.status,
            "conclusion": response.conclusion,
        }

    return handle


def registered_handlers(
    session: Session,
    settings: Settings,
) -> Mapping[str, JobHandler]:
    """Return the fixed allowlist; job payloads can never select callables."""

    github_handler = github_check_publish_handler(session, settings)

    def traced_github_handler(
        raw_payload: Mapping[str, Any],
        context: JobContext,
    ) -> Mapping[str, Any] | None:
        raw_carrier = raw_payload.get("trace_context", {})
        carrier = raw_carrier if isinstance(raw_carrier, Mapping) else {}
        token = attach_trace_context(carrier)
        try:
            with trace.get_tracer("deployguard.worker").start_as_current_span(
                "process background job",
                kind=SpanKind.CONSUMER,
                attributes={
                    "messaging.operation.type": "process",
                    "messaging.message.type": GITHUB_CHECK_PUBLISH_JOB,
                    "messaging.message.receive.count": context.attempt,
                },
            ):
                return github_handler(raw_payload, context)
        finally:
            detach_trace_context(token)

    return {GITHUB_CHECK_PUBLISH_JOB: traced_github_handler}


def _log_job(job) -> None:
    trace_context = (
        job.payload.get("trace_context")
        if isinstance(job.payload, dict)
        else None
    )
    logger.info(
        json.dumps(
            {
                "event": "background_job_finished",
                "job_id": job.id,
                "job_type": job.job_type,
                "workspace_id": job.workspace_id,
                "request_id": job.request_id,
                "traceparent": (
                    trace_context.get("traceparent")
                    if isinstance(trace_context, dict)
                    else None
                ),
                "attempt": job.attempts,
                "status": job.status,
            },
            separators=(",", ":"),
        )
    )


def run_worker(
    database: Database,
    settings: Settings,
    *,
    worker_id: str,
    stop_event: Event,
    poll_interval_seconds: float = 1.0,
    lease_timeout_seconds: float = 300.0,
    max_jobs: int | None = None,
    exit_when_idle: bool = False,
) -> int:
    """Run a bounded, cancellation-friendly worker polling loop."""

    if poll_interval_seconds < 0:
        raise ValueError("poll_interval_seconds cannot be negative")
    if lease_timeout_seconds <= 0:
        raise ValueError("lease_timeout_seconds must be positive")
    if max_jobs is not None and max_jobs < 1:
        raise ValueError("max_jobs must be positive when provided")

    processed = 0
    while not stop_event.is_set():
        with database.session_factory() as session:
            requeue_expired_jobs(
                session,
                lease_timeout=timedelta(seconds=lease_timeout_seconds),
            )
            job = run_one_job(
                session,
                worker_id=worker_id,
                handlers=registered_handlers(session, settings),
            )
            if job is not None:
                _log_job(job)
                processed += 1
        if max_jobs is not None and processed >= max_jobs:
            break
        if job is None:
            if exit_when_idle:
                break
            stop_event.wait(poll_interval_seconds)
    return processed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the DeployGuard job worker")
    parser.add_argument(
        "--worker-id",
        default=f"{socket.gethostname()}:{os.getpid()}",
    )
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--lease-timeout", type=float, default=300.0)
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run schema migrations before polling (normally done by release tooling)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()
    configure_tracing(settings)
    database = Database(settings.database_url)
    stop_event = Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        if args.migrate:
            if settings.environment.strip().lower() == "production":
                raise RuntimeError(
                    "The long-lived production worker cannot run migrations; "
                    "use python -m app.migrate with the schema-owner URL"
                )
            database.migrate(
                allow_legacy_bootstrap=settings.environment.lower()
                in {"development", "test", "container"}
            )
        else:
            database.require_migration_head()
        if settings.environment.strip().lower() == "production":
            database.require_postgresql_runtime_security()
        run_worker(
            database,
            settings,
            worker_id=args.worker_id,
            stop_event=stop_event,
            poll_interval_seconds=args.poll_interval,
            lease_timeout_seconds=args.lease_timeout,
            max_jobs=1 if args.once else args.max_jobs,
            exit_when_idle=args.once,
        )
    finally:
        database.dispose()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the process runner
    raise SystemExit(main())
