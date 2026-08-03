from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import select

from app import provider_services
from app.config import Settings
from app.database import Database
from app.engines import (
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    RISK_SCORING_POLICY_VERSION,
)
from app.job_contracts import (
    GITHUB_CHECK_PUBLISH_JOB,
    GitHubCheckPublishPayload,
    validated_trace_context,
)
from app.job_producers import enqueue_github_check_publication
from app.job_queue import (
    JobContext,
    claim_next_job,
    enqueue_job,
    requeue_expired_jobs,
    run_one_job,
)
from app.models import (
    AuditEvent,
    ChangeRecord,
    Repository,
    Scenario,
    User,
    Workspace,
)
from app.provider_models import GitHubCheckPublication, ProviderConnection
from app.worker import registered_handlers, run_worker


class SimulatedWorkerCrash(BaseException):
    """Model process termination, which application exception handlers skip."""


class RecordingGitHubClient:
    def __init__(self) -> None:
        self.create_calls = 0
        self.find_calls = 0
        self.update_calls = 0
        self.external_check_id: int | None = None
        self.crash_after_create = True

    def create_check_run(self, **payload) -> dict:
        self.create_calls += 1
        self.external_check_id = 4242
        if self.crash_after_create:
            self.crash_after_create = False
            raise SimulatedWorkerCrash
        return {
            "id": self.external_check_id,
            "status": "completed",
            "conclusion": payload["conclusion"],
        }

    def update_check_run(self, **payload) -> dict:
        self.update_calls += 1
        return {
            "id": int(payload["provider_check_id"]),
            "status": "completed",
            "conclusion": payload["conclusion"],
        }

    def find_check_run(self, **_payload) -> dict | None:
        self.find_calls += 1
        if self.external_check_id is None:
            return None
        return {"id": self.external_check_id}


def _worker_fixture(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'worker.db').as_posix()}"
    settings = Settings(
        database_url=database_url,
        github_app_id="app-id",
        github_app_slug="deployguard",
        github_app_private_key="test-key",
        github_checks_enabled=True,
        _env_file=None,
    )
    database = Database(database_url)
    database.migrate(allow_legacy_bootstrap=True)
    timestamp = datetime.now(UTC)
    with database.session_factory() as session:
        user = User(
            id="user-worker",
            email="worker@example.com",
            display_name="Worker owner",
            auth_provider="oidc",
            provider_subject="worker-subject",
            is_active=True,
            created_at=timestamp,
        )
        workspace = Workspace(
            id="workspace-worker",
            name="Worker workspace",
            slug="worker-workspace",
            created_by_user_id=user.id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        repository = Repository(
            id="repository-worker",
            workspace_id=workspace.id,
            provider="github",
            provider_repository_id="701",
            full_name="acme/checkout",
            default_branch="main",
            visibility="private",
            connection_state="connected",
            data_mode="connected",
            selected=True,
            last_synced_at=timestamp,
            created_at=timestamp,
        )
        scenario = Scenario(
            id="scenario-worker",
            workspace_id=workspace.id,
            repository_id=repository.id,
            name="Connected checkout",
            description="Connected evidence",
            data_mode="connected",
            is_active=True,
            sort_order=1,
            active_change_id="change-worker",
            active_incident_id=None,
            service_graph={"nodes": [], "edges": []},
        )
        change = ChangeRecord(
            id="change-worker",
            workspace_id=workspace.id,
            repository_id=repository.id,
            scenario_id=scenario.id,
            data_mode="connected",
            analysis_schema_version=ANALYSIS_SCHEMA_VERSION,
            engine_version=ENGINE_VERSION,
            scoring_policy_version=RISK_SCORING_POLICY_VERSION,
            graph_version=GRAPH_VERSION,
            title="Make retry behavior bounded",
            repository=repository.full_name,
            author="octocat",
            commit_sha="a" * 40,
            branch="main",
            created_at=timestamp,
            deployment_status="not_deployed",
            deployment_environment="unknown",
            changed_services=["checkout"],
            files_changed=3,
            lines_added=50,
            lines_deleted=10,
            flags=[],
            test_coverage=0.9,
            rollback_ready=True,
            observability_score=0.8,
            previous_failures=0,
            risk={
                "overall_score": 20,
                "level": "low",
                "data_quality": 1.0,
                "recommendations": [],
            },
            blast_radius={"nodes": [], "edges": []},
        )
        connection = ProviderConnection(
            id="connection-worker",
            workspace_id=workspace.id,
            provider="github",
            installation_id="12345",
            external_account_id="99",
            external_account_login="acme",
            external_account_type="Organization",
            connection_state="connected",
            permissions={"checks": "write"},
            repository_selection="selected",
            created_by_user_id=user.id,
            created_at=timestamp,
            updated_at=timestamp,
            last_synced_at=timestamp,
            error_code=None,
        )
        session.add_all([user, workspace, repository, scenario, change, connection])
        session.commit()
    return database, settings


def test_trace_context_is_validated_before_persistence() -> None:
    valid = validated_trace_context(
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "vendor=value",
    )
    assert valid is not None
    assert valid.tracestate == "vendor=value"
    assert validated_trace_context("00-not-valid", "vendor=value") is None


def test_worker_loop_is_bounded_when_idle(tmp_path: Path) -> None:
    database, settings = _worker_fixture(tmp_path)
    try:
        assert run_worker(
            database,
            settings,
            worker_id="worker-once",
            stop_event=Event(),
            poll_interval_seconds=0,
            max_jobs=1,
            exit_when_idle=True,
        ) == 0
    finally:
        database.dispose()


def test_worker_retry_after_crash_updates_existing_check_without_duplicate_create(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, settings = _worker_fixture(tmp_path)
    fake = RecordingGitHubClient()
    monkeypatch.setattr(provider_services, "github_client", lambda _settings: fake)
    try:
        with database.session_factory() as session:
            connection = session.get(ProviderConnection, "connection-worker")
            repository = session.get(Repository, "repository-worker")
            change = session.get(ChangeRecord, "change-worker")
            assert connection is not None and repository is not None and change is not None
            queued = enqueue_github_check_publication(
                session,
                connection=connection,
                repository=repository,
                change=change,
                request_id="request-worker-1",
                settings=settings,
                traceparent=(
                    "00-4bf92f3577b34da6a3ce929d0e0e4736-"
                    "00f067aa0ba902b7-01"
                ),
                tracestate="vendor=value",
                commit=True,
            )
            assert queued is not None
            assert queued.status == "queued"
            payload = GitHubCheckPublishPayload.model_validate(queued.payload)
            assert payload.trace_context is not None

            claimed = claim_next_job(session, worker_id="worker-crash")
            assert claimed is not None and claimed.locked_at is not None
            handler = registered_handlers(session, settings)[GITHUB_CHECK_PUBLISH_JOB]
            with pytest.raises(SimulatedWorkerCrash):
                handler(
                    claimed.payload,
                    JobContext(
                        job_id=claimed.id,
                        job_type=claimed.job_type,
                        workspace_id=claimed.workspace_id,
                        request_id=claimed.request_id,
                        attempt=claimed.attempts,
                    ),
                )
            # The provider accepted the create, but the process died before
            # publication state or the queue row could be acknowledged.
            assert session.get(type(claimed), claimed.id).status == "running"
            uncertain = session.scalar(select(GitHubCheckPublication))
            assert uncertain is not None
            assert uncertain.status == "publishing"
            assert uncertain.provider_check_id is None
            locked_at = claimed.locked_at

        with database.session_factory() as session:
            recovered = requeue_expired_jobs(
                session,
                lease_timeout=timedelta(seconds=1),
                now=locked_at.replace(tzinfo=UTC) + timedelta(seconds=2),
            )
            assert recovered == 1
            completed = run_one_job(
                session,
                worker_id="worker-retry",
                handlers=registered_handlers(session, settings),
                now=locked_at.replace(tzinfo=UTC) + timedelta(seconds=2),
            )
            assert completed is not None
            assert completed.status == "succeeded"
            assert completed.attempts == 2
            publication = session.scalar(select(GitHubCheckPublication))
            assert publication is not None
            assert publication.provider_check_id == "4242"
            audits = session.scalars(
                select(AuditEvent).where(
                    AuditEvent.request_id == "request-worker-1"
                )
            ).all()
            assert len(audits) == 1
        assert fake.create_calls == 1
        assert fake.find_calls == 1
        assert fake.update_calls == 1
    finally:
        database.dispose()


def test_worker_rejects_unknown_or_cross_tenant_payloads(
    tmp_path: Path,
) -> None:
    database, settings = _worker_fixture(tmp_path)
    try:
        with database.session_factory() as session:
            unknown = enqueue_job(
                session,
                job_type="unsafe.payload.selected.handler",
                payload={"handler": "github.check.publish.v1"},
            )
            failed = run_one_job(
                session,
                worker_id="worker-secure",
                handlers=registered_handlers(session, settings),
            )
            assert failed is not None
            assert failed.id == unknown.id
            assert failed.status == "failed"

            owner = session.get(User, "user-worker")
            assert owner is not None
            session.add(
                Workspace(
                    id="different-workspace",
                    name="Different workspace",
                    slug="different-workspace",
                    created_by_user_id=owner.id,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            session.commit()
            cross_tenant = enqueue_job(
                session,
                job_type=GITHUB_CHECK_PUBLISH_JOB,
                workspace_id="different-workspace",
                payload={
                    "schema_version": 1,
                    "connection_id": "connection-worker",
                    "repository_id": "repository-worker",
                    "change_id": "change-worker",
                },
            )
            rejected = run_one_job(
                session,
                worker_id="worker-secure",
                handlers=registered_handlers(session, settings),
            )
            assert rejected is not None
            assert rejected.id == cross_tenant.id
            assert rejected.status == "failed"
            assert "cross-tenant" in (rejected.last_error or "")
    finally:
        database.dispose()
