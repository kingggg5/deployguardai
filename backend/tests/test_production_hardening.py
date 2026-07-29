from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import provider_services
from app.errors import DomainError
from app.models import ChangeRecord, Repository, Scenario, Workspace
from app.operations_models import OperationalEvent, WorkspaceRiskPolicy
from app.provider_models import (
    GitHubCheckPublication,
    ProviderConnection,
)
from app.schemas import AnalyzeChangeRequest
from app.services import (
    analyze_change,
    derive_telemetry_collector_token,
)


def _headers(
    client: TestClient, email: str = "hardening-owner@example.com"
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": email, "display_name": "Hardening Owner"},
    )
    assert response.status_code == 200
    return {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }


def _workspace(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str,
    slug: str,
) -> dict:
    response = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": name, "slug": slug},
    )
    assert response.status_code == 201
    return response.json()


def _repository(
    client: TestClient,
    headers: dict[str, str],
    workspace_id: str,
    full_name: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        headers=headers,
        json={
            "full_name": full_name,
            "default_branch": "main",
            "visibility": "private",
        },
    )
    assert response.status_code == 201
    return response.json()


def _service(
    client: TestClient,
    headers: dict[str, str],
    workspace_id: str,
    *,
    name: str,
    slug: str,
    repository_id: str | None = None,
    dependencies: list[str] | None = None,
    tier: str = "tier_2",
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/services",
        headers=headers,
        json={
            "name": name,
            "slug": slug,
            "description": f"{name} production service",
            "tier": tier,
            "lifecycle": "active",
            "owner_team": "Reliability",
            "repository_id": repository_id,
            "dependencies": dependencies or [],
            "runbook_url": "https://runbooks.example.com/service",
            "tags": ["production"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _telemetry_payload(service_reference: str, summary: str) -> dict:
    return {
        "source": "otel",
        "type": "metric",
        "service_id": service_reference,
        "summary": summary,
        "value": 1.25,
        "supports_hypothesis_ids": [],
        "contradicts_hypothesis_ids": [],
    }


def test_telemetry_collector_credentials_are_tenant_scoped(
    client: TestClient,
) -> None:
    headers = _headers(client)
    first = _workspace(
        client,
        headers,
        name="Collector One",
        slug="collector-one",
    )
    second = _workspace(
        client,
        headers,
        name="Collector Two",
        slug="collector-two",
    )
    first_repository = _repository(
        client, headers, first["id"], "acme/collector-one"
    )
    second_repository = _repository(
        client, headers, second["id"], "acme/collector-two"
    )
    first_service = _service(
        client,
        headers,
        first["id"],
        name="Collector One API",
        slug="collector-one-api",
        repository_id=first_repository["id"],
    )
    second_service = _service(
        client,
        headers,
        second["id"],
        name="Collector Two API",
        slug="collector-two-api",
        repository_id=second_repository["id"],
    )
    master = client.app.state.settings.telemetry_ingest_token
    first_token = derive_telemetry_collector_token(master, first["id"])
    first_ingest = client.post(
        "/api/v1/telemetry/events",
        headers={
            "Authorization": f"Bearer {first_token}",
            "X-DeployGuard-Workspace": first["id"],
            "X-DeployGuard-Repository": first_repository["id"],
            "X-DeployGuard-Event-ID": "collector-one-event",
        },
        json=_telemetry_payload(
            first_service["slug"], "Collector one latency increased"
        ),
    )
    assert first_ingest.status_code == 201
    assert first_ingest.json()["workspace_id"] == first["id"]
    assert first_ingest.json()["service_id"] == first_service["id"]

    cross_tenant = client.post(
        "/api/v1/telemetry/events",
        headers={
            "Authorization": f"Bearer {first_token}",
            "X-DeployGuard-Workspace": second["id"],
            "X-DeployGuard-Repository": second_repository["id"],
            "X-DeployGuard-Event-ID": "cross-tenant-event",
        },
        json=_telemetry_payload(
            second_service["slug"], "Attempted cross-tenant event"
        ),
    )
    assert cross_tenant.status_code == 401
    assert cross_tenant.json()["code"] == "invalid_telemetry_token"

    second_token = derive_telemetry_collector_token(master, second["id"])
    second_ingest = client.post(
        "/api/v1/telemetry/events",
        headers={
            "Authorization": f"Bearer {second_token}",
            "X-DeployGuard-Workspace": second["id"],
            "X-DeployGuard-Repository": second_repository["id"],
            "X-DeployGuard-Event-ID": "collector-two-event",
        },
        json=_telemetry_payload(
            second_service["id"], "Collector two saturation increased"
        ),
    )
    assert second_ingest.status_code == 201
    assert second_ingest.json()["workspace_id"] == second["id"]

    with client.app.state.database.session_factory() as session:
        first_events = session.scalar(
            select(func.count(OperationalEvent.id)).where(
                OperationalEvent.workspace_id == first["id"]
            )
        )
        second_events = session.scalar(
            select(func.count(OperationalEvent.id)).where(
                OperationalEvent.workspace_id == second["id"]
            )
        )
        assert first_events == 1
        assert second_events == 1
        assert session.scalar(
            select(OperationalEvent.source).where(
                OperationalEvent.workspace_id == first["id"]
            )
        ) == "telemetry"
        assert session.scalar(
            select(OperationalEvent.source).where(
                OperationalEvent.workspace_id == second["id"]
            )
        ) == "telemetry"
        assert session.scalar(
            select(OperationalEvent.id).where(
                OperationalEvent.provider_event_id
                == "cross-tenant-event"
            )
        ) is None


def _analysis_request(commit_sha: str) -> AnalyzeChangeRequest:
    return AnalyzeChangeRequest(
        title="Harden checkout retry handling",
        repository="acme/hardening",
        author="reliability",
        commit_sha=commit_sha,
        branch="main",
        files_changed=3,
        lines_added=40,
        lines_deleted=8,
        changed_services=["root-api"],
        flags=[],
        test_coverage=1.0,
        rollback_ready=True,
        observability_score=1.0,
        previous_failures=0,
    )


def _catalog_analysis_fixture(
    client: TestClient,
    *,
    commit_sha: str,
) -> tuple[dict, dict, dict, ChangeRecord]:
    headers = _headers(client, f"{commit_sha[:8]}@example.com")
    workspace = _workspace(
        client,
        headers,
        name=f"Hardening {commit_sha[:8]}",
        slug=f"hardening-{commit_sha[:8]}",
    )
    repository = _repository(
        client, headers, workspace["id"], "acme/hardening"
    )
    root = _service(
        client,
        headers,
        workspace["id"],
        name="Root API",
        slug="root-api",
        repository_id=repository["id"],
        tier="tier_4",
    )
    scenario_id = f"hardening-{repository['id']}"
    with client.app.state.database.session_factory() as session:
        session.add(
            Scenario(
                id=scenario_id,
                workspace_id=workspace["id"],
                repository_id=repository["id"],
                name="Hardening connected analysis",
                description="Connected topology test",
                data_mode="connected",
                is_active=True,
                sort_order=1,
                active_change_id=None,
                active_incident_id=None,
                service_graph={"nodes": [], "edges": []},
            )
        )
        session.commit()
        baseline = analyze_change(
            session,
            _analysis_request(commit_sha),
            workspace_id=workspace["id"],
            repository_id=repository["id"],
            scenario_id=scenario_id,
        )

    dependent = _service(
        client,
        headers,
        workspace["id"],
        name="Dependent Worker",
        slug="dependent-worker",
        dependencies=[root["id"]],
    )
    _service(
        client,
        headers,
        workspace["id"],
        name="Customer Edge",
        slug="customer-edge",
        dependencies=[dependent["id"]],
    )
    tier_update = client.patch(
        f"/api/v1/services/{root['id']}",
        headers=headers,
        json={"tier": "tier_1"},
    )
    assert tier_update.status_code == 200

    with client.app.state.database.session_factory() as session:
        enriched = analyze_change(
            session,
            _analysis_request(commit_sha),
            workspace_id=workspace["id"],
            repository_id=repository["id"],
            scenario_id=scenario_id,
        )
        assert enriched.id != baseline.id
        assert enriched.risk.overall_score > baseline.risk.overall_score
        assert enriched.changed_services == [root["id"]]
        assert {node.id for node in enriched.blast_radius.nodes} == {
            root["id"],
            dependent["id"],
            next(
                node.id
                for node in enriched.blast_radius.nodes
                if node.id not in {root["id"], dependent["id"]}
            ),
        }
        change = session.get(ChangeRecord, enriched.id)
        assert change is not None
        session.expunge(change)
    return workspace, repository, root, change


class FlakyCheckClient:
    def __init__(self) -> None:
        self.create_calls = 0
        self.find_calls = 0
        self.update_calls = 0
        self.summaries: list[str] = []
        self.fail_first = True

    def create_check_run(self, **payload) -> dict:
        self.create_calls += 1
        self.summaries.append(payload["summary"])
        if self.fail_first:
            self.fail_first = False
            raise DomainError(
                "GitHub is temporarily unavailable",
                "github_api_unavailable",
                502,
            )
        return {
            "id": 7_777,
            "status": "completed",
            "conclusion": payload["conclusion"],
        }

    def find_check_run(self, **_payload) -> None:
        self.find_calls += 1
        return None

    def update_check_run(self, **payload) -> dict:
        self.update_calls += 1
        self.summaries.append(payload["summary"])
        return {
            "id": int(payload["provider_check_id"]),
            "status": "completed",
            "conclusion": payload["conclusion"],
        }


def test_catalog_topology_drives_policy_and_check_publication_is_retryable(
    client: TestClient,
    monkeypatch,
) -> None:
    commit_sha = "a" * 40
    workspace, repository_payload, _, detached_change = (
        _catalog_analysis_fixture(client, commit_sha=commit_sha)
    )
    fake = FlakyCheckClient()
    monkeypatch.setattr(
        provider_services, "github_client", lambda _settings: fake
    )
    timestamp = datetime.now(UTC)
    connection_id = str(uuid4())
    with client.app.state.database.session_factory() as session:
        repository = session.get(Repository, repository_payload["id"])
        change = session.get(ChangeRecord, detached_change.id)
        workspace_record = session.get(Workspace, workspace["id"])
        assert (
            repository is not None
            and change is not None
            and workspace_record is not None
        )
        connection = ProviderConnection(
            id=connection_id,
            workspace_id=workspace["id"],
            provider="github",
            installation_id="hardening-installation",
            external_account_id="42",
            external_account_login="acme",
            external_account_type="Organization",
            connection_state="connected",
            permissions={"checks": "write"},
            repository_selection="selected",
            created_by_user_id=workspace_record.created_by_user_id,
            created_at=timestamp,
            updated_at=timestamp,
            last_synced_at=timestamp,
            error_code=None,
        )
        session.add_all(
            [
                connection,
                WorkspaceRiskPolicy(
                    workspace_id=workspace["id"],
                    enabled=True,
                    warn_threshold=99,
                    block_threshold=100,
                    require_tests=False,
                    require_rollback=False,
                    max_blast_radius=1,
                    version=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
            ]
        )
        session.commit()

        with pytest.raises(DomainError) as first_failure:
            provider_services._publish_github_change_check(
                session,
                connection=connection,
                repository=repository,
                change=change,
                actor_user_id=None,
                request_id="retry-attempt-1",
                settings=client.app.state.settings,
            )
        assert first_failure.value.code == "github_api_unavailable"
        failed = session.scalar(
            select(GitHubCheckPublication).where(
                GitHubCheckPublication.repository_id == repository.id,
                GitHubCheckPublication.head_sha == commit_sha,
            )
        )
        assert failed is not None
        assert failed.status == "retryable_failed"
        assert failed.attempt_count == 1
        assert failed.next_retry_at is not None

        published = provider_services._publish_github_change_check(
            session,
            connection=session.get(ProviderConnection, connection_id),
            repository=repository,
            change=change,
            actor_user_id=None,
            request_id="retry-attempt-2",
            settings=client.app.state.settings,
        )
        assert published.provider_check_id == "7777"
        assert "change=" + change.id in published.details_url
        assert "workspace=" + workspace["id"] in published.details_url
        assert any(
            "Blast radius exceeds the workspace maximum" in summary
            for summary in fake.summaries
        )

        repeated = provider_services._publish_github_change_check(
            session,
            connection=session.get(ProviderConnection, connection_id),
            repository=repository,
            change=change,
            actor_user_id=None,
            request_id="repeat-publish",
            settings=client.app.state.settings,
        )
        assert repeated.provider_check_id == published.provider_check_id
        publication = session.scalar(
            select(GitHubCheckPublication).where(
                GitHubCheckPublication.repository_id == repository.id,
                GitHubCheckPublication.head_sha == commit_sha,
            )
        )
        assert publication is not None
        assert publication.status == "published"
        assert publication.attempt_count == 3
        assert publication.provider_check_id == "7777"
        assert fake.create_calls == 2
        assert fake.find_calls == 1
        assert fake.update_calls == 1
