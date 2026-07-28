import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import provider_services
from app.models import ChangeRecord


class FakeGitHubClient:
    def installation(self, installation_id: str) -> dict:
        assert installation_id == "12345"
        return {
            "account": {"id": 99, "login": "acme", "type": "Organization"},
            "permissions": {
                "metadata": "read",
                "pull_requests": "read",
                "deployments": "read",
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
    monkeypatch.setattr(
        provider_services, "github_client", lambda _settings: FakeGitHubClient()
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

    pull_request_body = json.dumps(
        {
            "action": "opened",
            "installation": {"id": 12345},
            "repository": {"id": 701, "full_name": "acme/checkout"},
            "pull_request": {
                "title": "Reduce checkout retry pressure",
                "user": {"login": "octocat"},
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
    analyzed = client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "pull-request-delivery-1",
            "X-Hub-Signature-256": pull_request_signature,
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
    listed_changes = client.get(
        f"/api/v1/workspaces/{workspace_id}/repositories/{connected[0]['id']}/changes",
        headers=headers,
    )
    assert listed_changes.status_code == 200
    assert listed_changes.json()[0]["id"] == analyzed.json()["change_id"]
