import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.deployment_models import DeploymentRecord
from app.models import (
    ChangeRecord,
    Repository,
    Scenario,
    User,
    UserContext,
    WorkspaceMembership,
)
from app.provider_models import ProviderConnection


def _development_session(
    client: TestClient,
    email: str,
    display_name: str,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": email, "display_name": display_name},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _signed_webhook(
    client: TestClient,
    *,
    event_type: str,
    delivery_id: str,
    payload: dict,
):
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(
        b"test-github-secret",
        body,
        hashlib.sha256,
    ).hexdigest()
    return client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-GitHub-Event": event_type,
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
        content=body,
    )


def _connected_fixture(
    client: TestClient,
) -> tuple[dict[str, str], str, str, str]:
    owner_headers = _development_session(
        client,
        "deployment-owner@example.com",
        "Deployment Owner",
    )
    workspace_response = client.post(
        "/api/v1/workspaces",
        headers=owner_headers,
        json={
            "name": "Deployment Platform",
            "slug": "deployment-platform",
        },
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]
    repository_id = str(uuid4())
    scenario_id = f"scenario-{uuid4()}"
    commit_sha = "a" * 40
    now = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)

    with client.app.state.database.session_factory() as session:
        owner = session.scalar(
            select(User).where(
                User.email == "deployment-owner@example.com"
            )
        )
        assert owner is not None
        repository = Repository(
            id=repository_id,
            workspace_id=workspace_id,
            provider="github",
            provider_repository_id="7701",
            full_name="acme/deployment-platform",
            default_branch="main",
            visibility="private",
            connection_state="connected",
            data_mode="connected",
            selected=True,
            last_synced_at=now,
            created_at=now,
        )
        session.add(repository)
        session.add(
            ProviderConnection(
                id=str(uuid4()),
                workspace_id=workspace_id,
                provider="github",
                installation_id="98765",
                external_account_id="99",
                external_account_login="acme",
                external_account_type="Organization",
                connection_state="connected",
                permissions={
                    "metadata": "read",
                    "deployments": "read",
                },
                repository_selection="selected",
                created_by_user_id=owner.id,
                created_at=now,
                updated_at=now,
                last_synced_at=now,
                error_code=None,
            )
        )
        session.add(
            Scenario(
                id=scenario_id,
                workspace_id=workspace_id,
                repository_id=repository_id,
                name="Connected deployment",
                description="Connected deployment test context",
                data_mode="connected",
                is_active=True,
                sort_order=0,
                active_change_id="change-exact-sha",
                active_incident_id=None,
                service_graph={"nodes": [], "edges": []},
            )
        )
        session.add(
            ChangeRecord(
                id="change-exact-sha",
                workspace_id=workspace_id,
                repository_id=repository_id,
                scenario_id=scenario_id,
                data_mode="connected",
                title="Deploy exact commit",
                repository="acme/deployment-platform",
                author="octocat",
                commit_sha=commit_sha,
                branch="main",
                created_at=now,
                deployment_status="not_deployed",
                deployment_environment="staging",
                changed_services=[],
                files_changed=2,
                lines_added=20,
                lines_deleted=4,
                flags=[],
                test_coverage=0.9,
                rollback_ready=True,
                observability_score=0.8,
                previous_failures=0,
                risk={},
                blast_radius={},
            )
        )
        session.commit()
    return owner_headers, workspace_id, repository_id, commit_sha


def test_github_deployment_is_canonical_idempotent_and_links_exact_sha(
    client: TestClient,
) -> None:
    owner_headers, workspace_id, repository_id, commit_sha = (
        _connected_fixture(client)
    )
    deployment_payload = {
        "action": "created",
        "installation": {"id": 98765},
        "repository": {
            "id": 7701,
            "full_name": "acme/deployment-platform",
        },
        "deployment": {
            "id": 4242,
            "sha": commit_sha,
            "ref": "main",
            "environment": "production",
            "created_at": "2026-07-30T01:05:00Z",
            "updated_at": "2026-07-30T01:05:00Z",
            "url": "https://api.github.example/deployments/4242",
        },
    }
    created = _signed_webhook(
        client,
        event_type="deployment",
        delivery_id="deployment-created-4242",
        payload=deployment_payload,
    )
    assert created.status_code == 200

    status_payload = {
        **deployment_payload,
        "action": "created",
        "deployment_status": {
            "id": 5001,
            "state": "success",
            "created_at": "2026-07-30T01:08:00Z",
            "environment_url": "https://app.example.com",
        },
    }
    completed = _signed_webhook(
        client,
        event_type="deployment_status",
        delivery_id="deployment-success-4242",
        payload=status_payload,
    )
    assert completed.status_code == 200

    replay = _signed_webhook(
        client,
        event_type="deployment_status",
        delivery_id="deployment-success-4242",
        payload=status_payload,
    )
    assert replay.status_code == 200
    assert "reconciled" in replay.json()["detail"]

    with client.app.state.database.session_factory() as session:
        assert (
            session.scalar(
                select(func.count(DeploymentRecord.id)).where(
                    DeploymentRecord.workspace_id == workspace_id
                )
            )
            == 1
        )
        deployment = session.scalar(
            select(DeploymentRecord).where(
                DeploymentRecord.workspace_id == workspace_id
            )
        )
        assert deployment is not None
        assert deployment.provider_deployment_id == "4242"
        assert deployment.repository_id == repository_id
        assert deployment.change_id == "change-exact-sha"
        assert deployment.commit_sha == commit_sha
        assert deployment.environment == "production"
        assert deployment.status == "succeeded"
        assert deployment.version == 2
        change = session.get(ChangeRecord, "change-exact-sha")
        assert change is not None
        assert change.deployment_status == "deployed"
        assert change.deployment_environment == "production"

    listed = client.get(
        f"/api/v1/workspaces/{workspace_id}/deployments",
        headers=owner_headers,
        params={"status": "succeeded"},
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["change_id"] == "change-exact-sha"


def test_connector_health_is_derived_and_tenant_scoped(
    client: TestClient,
) -> None:
    owner_headers, workspace_id, _, _ = _connected_fixture(client)
    viewer_headers = _development_session(
        client,
        "connector-viewer@example.com",
        "Connector Viewer",
    )
    outsider_headers = _development_session(
        client,
        "connector-outsider@example.com",
        "Connector Outsider",
    )
    with client.app.state.database.session_factory() as session:
        viewer = session.scalar(
            select(User).where(
                User.email == "connector-viewer@example.com"
            )
        )
        assert viewer is not None
        session.add(
            WorkspaceMembership(
                id=str(uuid4()),
                workspace_id=workspace_id,
                user_id=viewer.id,
                role="viewer",
                joined_at=datetime.now(UTC),
            )
        )
        context = session.get(UserContext, viewer.id)
        if context is not None:
            context.workspace_id = workspace_id
            context.repository_id = None
            context.scenario_id = None
            context.updated_at = datetime.now(UTC)
        session.commit()

    owner_health = client.get(
        f"/api/v1/workspaces/{workspace_id}/connectors",
        headers=owner_headers,
    )
    assert owner_health.status_code == 200
    assert owner_health.json()[0]["status"] == "healthy"
    assert owner_health.json()[0]["selected_resource_count"] == 1
    assert "installation_id" not in owner_health.json()[0]
    assert "permissions" not in owner_health.json()[0]

    viewer_health = client.get(
        f"/api/v1/workspaces/{workspace_id}/connectors",
        headers=viewer_headers,
    )
    assert viewer_health.status_code == 200

    with client.app.state.database.session_factory() as session:
        connection = session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.workspace_id == workspace_id
            )
        )
        assert connection is not None
        connection.error_code = "github_check_publish_failed"
        session.commit()
    degraded = client.get(
        f"/api/v1/workspaces/{workspace_id}/connectors",
        headers=owner_headers,
    )
    assert degraded.status_code == 200
    assert degraded.json()[0]["status"] == "degraded"
    assert "provider_error_recorded" in degraded.json()[0]["reasons"]

    outsider = client.get(
        f"/api/v1/workspaces/{workspace_id}/connectors",
        headers=outsider_headers,
    )
    assert outsider.status_code == 404
