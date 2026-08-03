from fastapi.testclient import TestClient
from sqlalchemy import select

from app.job_queue import enqueue_job, fail_job, claim_next_job
from app.models import AuditEvent


def _session(client: TestClient, email: str) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": email, "display_name": "Queue owner"},
    )
    assert response.status_code == 200
    payload = response.json()
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Queue operations", "slug": "queue-operations"},
    )
    assert workspace.status_code == 201
    return headers, workspace.json()["id"]


def test_admin_can_list_and_audit_replay_of_failed_workspace_job(
    client: TestClient,
) -> None:
    headers, workspace_id = _session(client, "queue-owner@example.com")
    database = client.app.state.database
    with database.session_factory() as session:
        job = enqueue_job(
            session,
            job_type="github.check.publish.v1",
            workspace_id=workspace_id,
            payload={"schema_version": 1},
        )
        claimed = claim_next_job(session, worker_id="api-test")
        assert claimed is not None
        failed = fail_job(
            session,
            claimed.id,
            error="provider configuration changed",
            retryable=False,
        )
        assert failed.status == "failed"

    listed = client.get(
        f"/api/v1/workspaces/{workspace_id}/jobs/attention",
        headers=headers,
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [job.id]
    assert "payload" not in listed.json()[0]
    assert "last_error" not in listed.json()[0]

    replayed = client.post(
        f"/api/v1/workspaces/{workspace_id}/jobs/{job.id}/replay",
        headers={**headers, "X-Request-ID": "job-replay-test"},
    )
    assert replayed.status_code == 200
    assert replayed.json()["status"] == "queued"
    assert replayed.json()["attempts"] == 0

    replay_again = client.post(
        f"/api/v1/workspaces/{workspace_id}/jobs/{job.id}/replay",
        headers=headers,
    )
    assert replay_again.status_code == 409

    with database.session_factory() as session:
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "background_job.replayed",
                AuditEvent.resource_id == job.id,
            )
        )
        assert audit is not None
        assert audit.request_id == "job-replay-test"
