from datetime import UTC, datetime

from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text

from app.models import LEGACY_WORKSPACE_ID
from app.operations_models import OperationalEvent


def session_headers(
    client: TestClient,
    email: str,
    display_name: str,
) -> tuple[dict[str, str], dict]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": email, "display_name": display_name},
    )
    assert response.status_code == 200
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload


def create_workspace(
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


def create_repository(
    client: TestClient,
    headers: dict[str, str],
    workspace_id: str,
    name: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        headers=headers,
        json={
            "full_name": name,
            "default_branch": "main",
            "visibility": "private",
        },
    )
    assert response.status_code == 201
    return response.json()


def add_member(
    client: TestClient,
    owner_headers: dict[str, str],
    workspace_id: str,
    *,
    email: str,
    role: str,
) -> tuple[dict[str, str], dict]:
    invitation_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
        json={"email": email, "role": role},
    )
    assert invitation_response.status_code == 201
    invitation = invitation_response.json()
    member_headers, member_session = session_headers(
        client, email, email.split("@")[0]
    )
    accepted = client.post(
        "/api/v1/invitations/accept",
        headers=member_headers,
        json={"token": invitation["claim_token"]},
    )
    assert accepted.status_code == 200
    return member_headers, member_session


def service_payload(
    *,
    name: str,
    slug: str,
    repository_id: str | None = None,
    dependencies: list[str] | None = None,
) -> dict:
    return {
        "name": name,
        "slug": slug,
        "description": f"{name} service",
        "tier": "tier_1",
        "lifecycle": "active",
        "owner_team": "Platform",
        "repository_id": repository_id,
        "dependencies": dependencies or [],
        "runbook_url": "https://runbooks.example.com/service",
        "tags": ["production", "payments"],
    }


def event_payload(
    *,
    event_id: str,
    repository_id: str | None = None,
    service_id: str | None = None,
    summary: str = "Checkout latency exceeded its objective",
) -> dict:
    return {
        "provider_event_id": event_id,
        "repository_id": repository_id,
        "service_id": service_id,
        "incident_id": None,
        "source": "manual",
        "event_type": "workflow_run.completed",
        "occurred_at": datetime.now(UTC).isoformat(),
        "severity": "warning",
        "summary": summary,
        "attributes": {"conclusion": "failure"},
        "provenance": {
            "provider": "github",
            "signature_verified": True,
        },
    }


def test_service_catalog_dependencies_tenant_isolation_and_rbac(
    client: TestClient,
) -> None:
    owner_headers, _ = session_headers(
        client, "catalog-owner@example.com", "Catalog Owner"
    )
    workspace = create_workspace(
        client,
        owner_headers,
        name="Catalog Workspace",
        slug="catalog-workspace",
    )
    repository = create_repository(
        client,
        owner_headers,
        workspace["id"],
        "acme/catalog",
    )

    api_response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/services",
        headers=owner_headers,
        json=service_payload(
            name="Public API",
            slug="public-api",
            repository_id=repository["id"],
        ),
    )
    assert api_response.status_code == 201
    api_service = api_response.json()

    worker_response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/services",
        headers=owner_headers,
        json=service_payload(
            name="Worker",
            slug="worker",
            dependencies=[api_service["id"]],
        ),
    )
    assert worker_response.status_code == 201
    worker = worker_response.json()
    assert worker["dependencies"] == [api_service["id"]]

    self_dependency = client.patch(
        f"/api/v1/services/{api_service['id']}",
        headers=owner_headers,
        json={"dependencies": [api_service["id"]]},
    )
    assert self_dependency.status_code == 422
    assert self_dependency.json()["code"] == "service_self_dependency"

    cycle = client.patch(
        f"/api/v1/services/{api_service['id']}",
        headers=owner_headers,
        json={"dependencies": [worker["id"]]},
    )
    assert cycle.status_code == 422
    assert cycle.json()["code"] == "service_dependency_cycle"

    second_workspace = create_workspace(
        client,
        owner_headers,
        name="Other Catalog",
        slug="other-catalog",
    )
    foreign_service = client.post(
        f"/api/v1/workspaces/{second_workspace['id']}/services",
        headers=owner_headers,
        json=service_payload(name="Foreign", slug="foreign"),
    ).json()
    cross_workspace_dependency = client.patch(
        f"/api/v1/services/{api_service['id']}",
        headers=owner_headers,
        json={"dependencies": [foreign_service["id"]]},
    )
    assert cross_workspace_dependency.status_code == 422
    assert (
        cross_workspace_dependency.json()["code"]
        == "invalid_service_dependency"
    )

    viewer_headers, _ = add_member(
        client,
        owner_headers,
        workspace["id"],
        email="catalog-viewer@example.com",
        role="viewer",
    )
    assert client.get(
        f"/api/v1/workspaces/{workspace['id']}/services",
        headers=viewer_headers,
    ).status_code == 200
    assert client.post(
        f"/api/v1/workspaces/{workspace['id']}/services",
        headers=viewer_headers,
        json=service_payload(name="Forbidden", slug="forbidden"),
    ).status_code == 403

    outsider_headers, _ = session_headers(
        client, "catalog-outsider@example.com", "Outsider"
    )
    cross_tenant_get = client.get(
        f"/api/v1/services/{api_service['id']}",
        headers=outsider_headers,
    )
    assert cross_tenant_get.status_code == 404
    assert cross_tenant_get.json()["code"] == "workspace_not_found"


def test_risk_policy_validation_versioning_and_rbac(
    client: TestClient,
) -> None:
    owner_headers, _ = session_headers(
        client, "policy-owner@example.com", "Policy Owner"
    )
    workspace = create_workspace(
        client,
        owner_headers,
        name="Policy Workspace",
        slug="policy-workspace",
    )
    policy_url = f"/api/v1/workspaces/{workspace['id']}/risk-policy"

    initial = client.get(policy_url, headers=owner_headers)
    assert initial.status_code == 200
    assert initial.json() == {
        "enabled": True,
        "warn_threshold": 60,
        "block_threshold": 80,
        "require_tests": True,
        "require_rollback": True,
        "max_blast_radius": 10,
        "version": 1,
        "created_at": initial.json()["created_at"],
        "updated_at": initial.json()["updated_at"],
    }

    invalid_thresholds = client.put(
        policy_url,
        headers=owner_headers,
        json={
            "enabled": True,
            "warn_threshold": 90,
            "block_threshold": 80,
            "require_tests": True,
            "require_rollback": True,
            "max_blast_radius": 10,
            "version": 2,
        },
    )
    assert invalid_thresholds.status_code == 422

    updated = client.put(
        policy_url,
        headers=owner_headers,
        json={
            "enabled": True,
            "warn_threshold": 55,
            "block_threshold": 85,
            "require_tests": True,
            "require_rollback": False,
            "max_blast_radius": 20,
            "version": 2,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["warn_threshold"] == 55

    stale = client.put(
        policy_url,
        headers=owner_headers,
        json={
            "enabled": False,
            "warn_threshold": 40,
            "block_threshold": 70,
            "require_tests": False,
            "require_rollback": False,
            "max_blast_radius": 30,
            "version": 2,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "risk_policy_version_conflict"

    viewer_headers, _ = add_member(
        client,
        owner_headers,
        workspace["id"],
        email="policy-viewer@example.com",
        role="viewer",
    )
    assert client.get(policy_url, headers=viewer_headers).status_code == 200
    denied = client.put(
        policy_url,
        headers=viewer_headers,
        json={
            "enabled": True,
            "warn_threshold": 50,
            "block_threshold": 80,
            "require_tests": True,
            "require_rollback": True,
            "max_blast_radius": 10,
            "version": 3,
        },
    )
    assert denied.status_code == 403


def test_operational_event_ingestion_dedupe_filters_and_security_bounds(
    client: TestClient,
) -> None:
    owner_headers, _ = session_headers(
        client, "events-owner@example.com", "Events Owner"
    )
    workspace = create_workspace(
        client,
        owner_headers,
        name="Events Workspace",
        slug="events-workspace",
    )
    repository = create_repository(
        client, owner_headers, workspace["id"], "acme/events"
    )
    service = client.post(
        f"/api/v1/workspaces/{workspace['id']}/services",
        headers=owner_headers,
        json=service_payload(
            name="Checkout",
            slug="checkout",
            repository_id=repository["id"],
        ),
    ).json()
    events_url = f"/api/v1/workspaces/{workspace['id']}/events"
    payload = event_payload(
        event_id="delivery-001",
        repository_id=repository["id"],
        service_id=service["id"],
    )

    created = client.post(events_url, headers=owner_headers, json=payload)
    assert created.status_code == 201
    assert created.json()["source"] == "manual"
    assert created.json()["ingestion_status"] == "accepted"
    assert created.json()["provenance"]["_ingestion"]["channel"] == (
        "member_api"
    )
    assert created.json()["provenance"]["origin"] == (
        "authenticated_member"
    )
    assert "signature_verified" not in created.json()["provenance"]

    replayed = client.post(events_url, headers=owner_headers, json=payload)
    assert replayed.status_code == 201
    assert replayed.json()["id"] == created.json()["id"]

    untrusted_provenance_replay = client.post(
        events_url,
        headers=owner_headers,
        json={
            **payload,
            "provenance": {
                "provider": "github",
                "signature_verified": False,
                "attempted_override": True,
            },
        },
    )
    assert untrusted_provenance_replay.status_code == 201
    assert untrusted_provenance_replay.json()["id"] == created.json()["id"]
    assert "attempted_override" not in (
        untrusted_provenance_replay.json()["provenance"]
    )

    replay_payload = {**payload, "summary": "Changed replay body"}
    replayed = client.post(
        events_url, headers=owner_headers, json=replay_payload
    )
    assert replayed.status_code == 409
    assert (
        replayed.json()["code"]
        == "operational_event_idempotency_conflict"
    )
    second_responder_headers, _ = add_member(
        client,
        owner_headers,
        workspace["id"],
        email="events-second-responder@example.com",
        role="responder",
    )
    conflicting_origin = client.post(
        events_url,
        headers=second_responder_headers,
        json=payload,
    )
    assert conflicting_origin.status_code == 409
    assert (
        conflicting_origin.json()["code"]
        == "operational_event_idempotency_conflict"
    )
    with client.app.state.database.session_factory() as session:
        count = session.scalar(
            select(func.count(OperationalEvent.id)).where(
                OperationalEvent.workspace_id == workspace["id"]
            )
        )
    assert count == 1

    filtered = client.get(
        events_url,
        headers=owner_headers,
        params={
            "source": "MANUAL",
            "severity": "warning",
            "service_id": service["id"],
        },
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [created.json()["id"]]

    oversized = {
        **event_payload(event_id="delivery-large"),
        "attributes": {"payload": "x" * 65_537},
    }
    assert client.post(
        events_url, headers=owner_headers, json=oversized
    ).status_code == 422

    other_repository = create_repository(
        client, owner_headers, workspace["id"], "acme/other-events"
    )
    scope_mismatch = client.post(
        events_url,
        headers=owner_headers,
        json=event_payload(
            event_id="delivery-mismatch",
            repository_id=other_repository["id"],
            service_id=service["id"],
        ),
    )
    assert scope_mismatch.status_code == 422
    assert (
        scope_mismatch.json()["code"] == "operational_event_scope_mismatch"
    )

    for reserved_source in (
        "github",
        "github.actions",
        "telemetry",
        "otel-traces",
        "otlp",
        "opentelemetry/logs",
    ):
        impersonation = client.post(
            events_url,
            headers=owner_headers,
            json={
                **event_payload(
                    event_id=f"reserved-{reserved_source.replace('/', '-')}"
                ),
                "source": reserved_source,
            },
        )
        assert impersonation.status_code == 422
        assert (
            impersonation.json()["code"]
            == "operational_event_source_reserved"
        )

    derived_service_repository = client.post(
        events_url,
        headers=owner_headers,
        json=event_payload(
            event_id="service-derived-repository",
            service_id=service["id"],
        ),
    )
    assert derived_service_repository.status_code == 201
    assert (
        derived_service_repository.json()["repository_id"]
        == repository["id"]
    )

    viewer_headers, _ = add_member(
        client,
        owner_headers,
        workspace["id"],
        email="events-viewer@example.com",
        role="viewer",
    )
    assert client.get(events_url, headers=viewer_headers).status_code == 200
    assert client.post(
        events_url,
        headers=viewer_headers,
        json=event_payload(event_id="viewer-write"),
    ).status_code == 403

    outsider_headers, _ = session_headers(
        client, "events-outsider@example.com", "Events Outsider"
    )
    assert client.get(events_url, headers=outsider_headers).status_code == 404

    other_workspace = create_workspace(
        client,
        owner_headers,
        name="Second Events Workspace",
        slug="second-events-workspace",
    )
    same_provider_id_other_tenant = client.post(
        f"/api/v1/workspaces/{other_workspace['id']}/events",
        headers=owner_headers,
        json=event_payload(event_id="delivery-001"),
    )
    assert same_provider_id_other_tenant.status_code == 201
    assert same_provider_id_other_tenant.json()["id"] != created.json()["id"]


def test_incident_lifecycle_timeline_notifications_and_tenant_scope(
    client: TestClient,
) -> None:
    owner_headers, owner_session = session_headers(
        client, "owner@deployguard.local", "Owner"
    )
    incidents = client.get("/api/v1/incidents", headers=owner_headers)
    assert incidents.status_code == 200
    incident_id = "inc-checkout-latency"
    correlated_event = client.post(
        f"/api/v1/workspaces/{LEGACY_WORKSPACE_ID}/events",
        headers=owner_headers,
        json={
            **event_payload(event_id="incident-correlation"),
            "incident_id": incident_id,
        },
    )
    assert correlated_event.status_code == 201
    assert correlated_event.json()["ingestion_status"] == "correlated"
    assert correlated_event.json()["repository_id"] is not None

    mismatched_repository = create_repository(
        client,
        owner_headers,
        LEGACY_WORKSPACE_ID,
        "acme/correlation-mismatch",
    )
    mismatched_service = client.post(
        f"/api/v1/workspaces/{LEGACY_WORKSPACE_ID}/services",
        headers=owner_headers,
        json=service_payload(
            name="Mismatched service",
            slug="mismatched-service",
            repository_id=mismatched_repository["id"],
        ),
    )
    assert mismatched_service.status_code == 201
    missing_repository_mismatch = client.post(
        f"/api/v1/workspaces/{LEGACY_WORKSPACE_ID}/events",
        headers=owner_headers,
        json={
            **event_payload(
                event_id="implicit-repository-mismatch",
                service_id=mismatched_service.json()["id"],
            ),
            "incident_id": incident_id,
            "repository_id": None,
        },
    )
    assert missing_repository_mismatch.status_code == 422
    assert (
        missing_repository_mismatch.json()["code"]
        == "operational_event_scope_mismatch"
    )

    responder_headers, responder_session = add_member(
        client,
        owner_headers,
        LEGACY_WORKSPACE_ID,
        email="incident-responder@example.com",
        role="responder",
    )
    viewer_headers, _ = add_member(
        client,
        owner_headers,
        LEGACY_WORKSPACE_ID,
        email="incident-viewer@example.com",
        role="viewer",
    )
    lifecycle_url = f"/api/v1/incidents/{incident_id}/lifecycle"

    assert client.patch(
        lifecycle_url,
        headers=viewer_headers,
        json={"status": "mitigated"},
    ).status_code == 403

    invalid_assignee = client.patch(
        lifecycle_url,
        headers=responder_headers,
        json={"assignee_user_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert invalid_assignee.status_code == 422
    assert invalid_assignee.json()["code"] == "invalid_incident_assignee"

    updated = client.patch(
        lifecycle_url,
        headers=responder_headers,
        json={
            "status": "mitigated",
            "severity": "sev2",
            "assignee_user_id": owner_session["user"]["id"],
        },
    )
    assert updated.status_code == 200
    lifecycle = updated.json()
    assert lifecycle["status"] == "mitigated"
    assert lifecycle["severity"] == "sev2"
    assert lifecycle["assignee_user_id"] == owner_session["user"]["id"]
    assert lifecycle["timeline"][-1]["actor_user_id"] == (
        responder_session["user"]["id"]
    )

    backwards = client.patch(
        lifecycle_url,
        headers=responder_headers,
        json={"status": "acknowledged"},
    )
    assert backwards.status_code == 409
    assert backwards.json()["code"] == "invalid_incident_transition"

    note = client.post(
        f"/api/v1/incidents/{incident_id}/notes",
        headers=responder_headers,
        json={"note": "Database saturation reproduced from connected traces."},
    )
    assert note.status_code == 201
    assert note.json()["type"] == "incident_note"
    assert note.json()["actor_user_id"] == responder_session["user"]["id"]
    detail = client.get(
        f"/api/v1/incidents/{incident_id}", headers=owner_headers
    )
    assert detail.status_code == 200
    assert detail.json()["timeline"][-1]["detail"].startswith(
        "Database saturation"
    )

    owner_notifications = client.get(
        "/api/v1/notifications",
        headers=owner_headers,
        params={"workspace_id": LEGACY_WORKSPACE_ID, "unread_only": True},
    )
    assert owner_notifications.status_code == 200
    assert {
        item["kind"] for item in owner_notifications.json()
    } == {"incident_lifecycle", "incident_note"}
    owner_notification_id = owner_notifications.json()[0]["id"]

    cross_recipient = client.patch(
        f"/api/v1/notifications/{owner_notification_id}/read",
        headers=responder_headers,
    )
    assert cross_recipient.status_code == 404
    read = client.patch(
        f"/api/v1/notifications/{owner_notification_id}/read",
        headers=owner_headers,
    )
    assert read.status_code == 200
    assert read.json()["read_at"] is not None

    resolved = client.patch(
        lifecycle_url,
        headers=responder_headers,
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None
    immutable = client.patch(
        lifecycle_url,
        headers=responder_headers,
        json={"severity": "sev3"},
    )
    assert immutable.status_code == 409
    assert immutable.json()["code"] == "incident_already_resolved"

    outsider_headers, _ = session_headers(
        client, "incident-outsider@example.com", "Incident Outsider"
    )
    create_workspace(
        client,
        outsider_headers,
        name="Outsider Workspace",
        slug="incident-outsider",
    )
    assert client.patch(
        lifecycle_url,
        headers=outsider_headers,
        json={"status": "mitigated"},
    ).status_code == 404


def test_operations_migration_is_at_head_and_schema_is_complete(
    client: TestClient,
) -> None:
    expected_head = ScriptDirectory.from_config(
        client.app.state.database._alembic_config()
    ).get_current_head()
    with client.app.state.database.engine.connect() as connection:
        assert connection.scalar(
            text("SELECT version_num FROM alembic_version")
        ) == expected_head
    inspector = inspect(client.app.state.database.engine)
    tables = set(inspector.get_table_names())
    assert {
        "services",
        "workspace_risk_policies",
        "operational_events",
        "notifications",
    }.issubset(tables)
    incident_columns = {
        column["name"] for column in inspector.get_columns("incidents")
    }
    assert "assignee_user_id" in incident_columns
