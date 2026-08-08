from __future__ import annotations

from fastapi.testclient import TestClient
from app.job_models import BackgroundJob


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": "notification-owner@example.com", "display_name": "Notification Owner"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_notification_delivery_is_allowlisted_and_idempotent(client: TestClient) -> None:
    headers = _headers(client)
    workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Notification Workspace", "slug": "notification-workspace"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]
    created_event = client.post(
        f"/api/v1/workspaces/{workspace_id}/events",
        headers=headers,
        json={
            "provider_event_id": "notification-outbox-test",
            "source": "manual",
            "event_type": "incident.triggered",
            "occurred_at": "2026-08-08T12:00:00Z",
            "severity": "critical",
            "summary": "Checkout error budget is exhausted",
            "attributes": {},
        },
    )
    assert created_event.status_code == 201
    event_id = created_event.json()["id"]

    unconfigured = client.post(
        f"/api/v1/workspaces/{workspace_id}/notification-deliveries",
        headers=headers,
        json={"provider": "slack", "event_id": event_id},
    )
    assert unconfigured.status_code == 503
    assert unconfigured.json()["code"] == "notification_provider_not_configured"

    client.app.state.settings.slack_webhook_url = "https://hooks.slack.com/services/test"
    queued = client.post(
        f"/api/v1/workspaces/{workspace_id}/notification-deliveries",
        headers=headers,
        json={"provider": "slack", "event_id": event_id},
    )
    assert queued.status_code == 202
    first = queued.json()
    assert first["provider"] == "slack"
    assert first["status"] == "queued"

    duplicate = client.post(
        f"/api/v1/workspaces/{workspace_id}/notification-deliveries",
        headers=headers,
        json={"provider": "slack", "event_id": event_id},
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["job_id"] == first["job_id"]

    with client.app.state.database.session_factory() as session:
        job = session.get(BackgroundJob, first["job_id"])
        assert job is not None
        assert job.workspace_id == workspace_id
        assert job.payload == {"schema_version": 1, "provider": "slack", "event_id": event_id}
        assert "webhook" not in str(job.payload)
