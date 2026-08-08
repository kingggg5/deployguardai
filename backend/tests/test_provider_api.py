import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import provider_services
from app.models import ChangeRecord
from app.engines import (
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    RISK_SCORING_POLICY_VERSION,
)
from app.job_contracts import GITHUB_CHECK_PUBLISH_JOB
from app.job_models import BackgroundJob
from app.operations_models import OperationalEvent
from app.provider_models import WebhookDelivery


class FakeGitHubClient:
    def __init__(self) -> None:
        self.create_calls = 0

    def installation(self, installation_id: str) -> dict:
        assert installation_id == "12345"
        return {
            "account": {"id": 99, "login": "acme", "type": "Organization"},
            "permissions": {
                "metadata": "read",
                "pull_requests": "read",
                "deployments": "read",
                "checks": "write",
            },
            "repository_selection": "selected",
        }

    def list_installation_repositories(
        self, installation_id: str
    ) -> list[dict]:
        assert installation_id == "12345"
        return [
            {
                "id": 701,
                "full_name": "acme/checkout",
                "default_branch": "main",
                "visibility": "private",
                "html_url": "https://github.com/acme/checkout",
                "archived": False,
                "pushed_at": "2026-07-28T00:00:00Z",
            }
        ]

    def create_check_run(self, **payload) -> dict:
        self.create_calls += 1
        assert payload["installation_id"] == "12345"
        assert payload["repository_full_name"] == "acme/checkout"
        assert len(payload["head_sha"]) >= 7
        assert payload["conclusion"] == "neutral"
        assert "No SHA-matched DeployGuard Evidence Receipt" in payload["summary"]
        assert "Metadata-derived risk prior" in payload["summary"]
        assert "decision support only" in payload["summary"]
        return {
            "id": 4_242,
            "status": "completed",
            "conclusion": payload["conclusion"],
        }


def _session(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": "github-owner@example.com", "display_name": "Owner"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_capabilities_are_truthful(client: TestClient) -> None:
    payload = client.get("/api/v1/capabilities").json()
    assert payload["development_identity"] is True
    assert payload["github_app"] is False
    assert payload["email_delivery"] == "development_outbox"


def test_github_install_discovery_and_sync(
    client: TestClient, monkeypatch
) -> None:
    settings = client.app.state.settings
    settings.github_app_id = "app-id"
    settings.github_app_slug = "deployguard-test"
    settings.github_app_private_key = "test-key"
    fake_github = FakeGitHubClient()
    monkeypatch.setattr(
        provider_services, "github_client", lambda _settings: fake_github
    )
    headers = _session(client)
    workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Connected Platform", "slug": "connected-platform"},
    ).json()
    workspace_id = workspace["id"]

    start = client.post(
        f"/api/v1/workspaces/{workspace_id}/providers/github/install",
        headers=headers,
    )
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["install_url"]).query)["state"][0]

    callback = client.get(
        "/api/v1/providers/github/callback",
        params={
            "installation_id": "12345",
            "setup_action": "install",
            "state": state,
        },
        follow_redirects=False,
    )
    assert callback.status_code == 303
    pending = client.get(
        f"/api/v1/workspaces/{workspace_id}/providers/github",
        headers=headers,
    )
    assert pending.json()["connection_state"] == "pending_verification"

    webhook_body = json.dumps(
        {
            "action": "created",
            "installation": {"id": 12345},
        },
        separators=(",", ":"),
    ).encode()
    webhook_signature = "sha256=" + hmac.new(
        b"test-github-secret", webhook_body, hashlib.sha256
    ).hexdigest()
    verified = client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-GitHub-Event": "installation",
            "X-GitHub-Delivery": "installation-delivery-1",
            "X-Hub-Signature-256": webhook_signature,
            "Content-Type": "application/json",
        },
        content=webhook_body,
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "accepted"

    replay = client.get(
        "/api/v1/providers/github/callback",
        params={
            "installation_id": "12345",
            "setup_action": "install",
            "state": state,
        },
        follow_redirects=False,
    )
    assert replay.status_code == 400

    repositories = client.get(
        f"/api/v1/workspaces/{workspace_id}/providers/github/repositories",
        headers=headers,
    )
    assert repositories.status_code == 200
    assert repositories.json()[0]["full_name"] == "acme/checkout"

    sync = client.post(
        f"/api/v1/workspaces/{workspace_id}/providers/github/repositories/sync",
        headers=headers,
        json={"repository_ids": ["701"]},
    )
    assert sync.status_code == 200
    assert sync.json()["imported"] == 1
    connected = client.get(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        headers=headers,
    ).json()
    assert connected[0]["provider"] == "github"
    assert connected[0]["data_mode"] == "connected"
    selected_context = client.put(
        "/api/v1/me/context",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "repository_id": connected[0]["id"],
            "scenario_id": f"github-{connected[0]['id']}",
        },
    )
    assert selected_context.status_code == 200

    pull_request_body = json.dumps(
        {
            "action": "opened",
            "installation": {"id": 12345},
            "repository": {"id": 701, "full_name": "acme/checkout"},
            "pull_request": {
                "title": "Reduce checkout retry pressure",
                "user": {"login": "octocat"},
                "head": {"sha": "b" * 40, "ref": "reduce-retries"},
                "changed_files": 4,
                "additions": 82,
                "deletions": 17,
                "labels": [{"name": "reliability"}],
            },
        },
        separators=(",", ":"),
    ).encode()
    pull_request_signature = "sha256=" + hmac.new(
        b"test-github-secret", pull_request_body, hashlib.sha256
    ).hexdigest()
    settings.github_checks_enabled = True
    traceparent = (
        "00-4bf92f3577b34da6a3ce929d0e0e4736-"
        "00f067aa0ba902b7-01"
    )
    analyzed = client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "pull-request-delivery-1",
            "X-Hub-Signature-256": pull_request_signature,
            "X-Request-ID": "github-pr-request-1",
            "traceparent": traceparent,
            "tracestate": "vendor=value",
            "Content-Type": "application/json",
        },
        content=pull_request_body,
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["change_id"].startswith("chg-analysis-")
    with client.app.state.database.session_factory() as session:
        change = session.scalar(
            select(ChangeRecord).where(
                ChangeRecord.id == analyzed.json()["change_id"]
            )
        )
        assert change is not None
        assert change.data_mode == "connected"
        assert change.repository == "acme/checkout"
        assert change.analysis_schema_version == ANALYSIS_SCHEMA_VERSION
        assert change.engine_version == ENGINE_VERSION
        assert change.scoring_policy_version == RISK_SCORING_POLICY_VERSION
        assert change.graph_version == GRAPH_VERSION
        queued = session.scalar(
            select(BackgroundJob).where(
                BackgroundJob.job_type == GITHUB_CHECK_PUBLISH_JOB,
                BackgroundJob.workspace_id == workspace_id,
            )
        )
        assert queued is not None
        assert queued.status == "queued"
        assert queued.request_id == "github-pr-request-1"
        assert queued.payload["change_id"] == change.id
        assert queued.payload["trace_context"] == {
            "traceparent": traceparent,
            "tracestate": "vendor=value",
        }
        delivery = session.scalar(
            select(WebhookDelivery).where(
                WebhookDelivery.delivery_id == "pull-request-delivery-1"
            )
        )
        assert delivery is not None
        assert delivery.status == "processed"
    # Provider I/O is never performed on the webhook request path.
    assert fake_github.create_calls == 0
    replayed_pr = client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "pull-request-delivery-1",
            "X-Hub-Signature-256": pull_request_signature,
            "Content-Type": "application/json",
        },
        content=pull_request_body,
    )
    assert replayed_pr.status_code == 200
    assert "already processed" in replayed_pr.json()["detail"]
    with client.app.state.database.session_factory() as session:
        queued_count = session.scalar(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.job_type == GITHUB_CHECK_PUBLISH_JOB,
                BackgroundJob.workspace_id == workspace_id,
            )
        )
        assert queued_count == 1
    listed_changes = client.get(
        f"/api/v1/workspaces/{workspace_id}/repositories/{connected[0]['id']}/changes",
        headers=headers,
    )
    assert listed_changes.status_code == 200
    assert listed_changes.json()[0]["id"] == analyzed.json()["change_id"]
    connected_overview = client.get("/api/v1/overview", headers=headers)
    assert connected_overview.status_code == 200
    assert connected_overview.json()["data_mode"] == "connected"
    assert connected_overview.json()["active_change"]["id"] == analyzed.json()["change_id"]
    assert connected_overview.json()["active_incident"] is None

    settings.github_checks_enabled = False
    disabled_check = client.post(
        (
            f"/api/v1/workspaces/{workspace_id}/repositories/"
            f"{connected[0]['id']}/changes/"
            f"{analyzed.json()['change_id']}/github-check"
        ),
        headers=headers,
    )
    assert disabled_check.status_code == 409
    assert disabled_check.json()["code"] == "github_checks_disabled"

    settings.github_checks_enabled = True
    published = client.post(
        (
            f"/api/v1/workspaces/{workspace_id}/repositories/"
            f"{connected[0]['id']}/changes/"
            f"{analyzed.json()['change_id']}/github-check"
        ),
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["provider_check_id"] == "4242"
    assert published.json()["change_id"] == analyzed.json()["change_id"]
    assert published.json()["status"] == "completed"
    assert published.json()["conclusion"] == "neutral"

    workflow_body = json.dumps(
        {
            "action": "completed",
            "installation": {"id": 12345},
            "repository": {"id": 701, "full_name": "acme/checkout"},
            "workflow_run": {
                "id": 8_801,
                "name": "Deploy checkout",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": "b" * 40,
                "head_branch": "main",
                "updated_at": "2026-07-28T05:04:03Z",
                "html_url": "https://github.example/runs/8801",
            },
        },
        separators=(",", ":"),
    ).encode()
    workflow_signature = "sha256=" + hmac.new(
        b"test-github-secret", workflow_body, hashlib.sha256
    ).hexdigest()
    workflow_headers = {
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "workflow-delivery-1",
        "X-Hub-Signature-256": workflow_signature,
        "Content-Type": "application/json",
    }
    workflow_event = client.post(
        "/api/v1/webhooks/github",
        headers=workflow_headers,
        content=workflow_body,
    )
    assert workflow_event.status_code == 200
    assert workflow_event.json()["status"] == "accepted"
    with client.app.state.database.session_factory() as session:
        stored_event = session.scalar(
            select(OperationalEvent).where(
                OperationalEvent.workspace_id == workspace_id,
                OperationalEvent.source == "github",
                OperationalEvent.provider_event_id == "workflow-delivery-1",
            )
        )
        assert stored_event is not None
        session.delete(stored_event)
        session.commit()
    workflow_replay = client.post(
        "/api/v1/webhooks/github",
        headers=workflow_headers,
        content=workflow_body,
    )
    assert workflow_replay.status_code == 200
    assert "reconciled" in workflow_replay.json()["detail"]
    events = client.get(
        f"/api/v1/workspaces/{workspace_id}/events",
        headers=headers,
        params={"source": "github", "event_type": "workflow_run"},
    )
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["severity"] == "error"
    assert events.json()[0]["attributes"]["workflow_id"] == 8_801
