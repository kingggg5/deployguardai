from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.job_models import BackgroundJob
from app.main import create_app
from app.models import Invitation


def development_session(
    client: TestClient,
    email: str = "owner@deployguard.local",
    display_name: str = "Owner",
) -> tuple[dict[str, str], dict]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": email, "display_name": display_name},
    )
    assert response.status_code == 200
    payload = response.json()
    assert response.headers["cache-control"] == "no-store"
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload


def test_workspace_repository_invitation_and_audit_flow(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/workspaces").status_code == 401
    owner_headers, _ = development_session(client)

    workspace_response = client.post(
        "/api/v1/workspaces",
        headers=owner_headers,
        json={"name": "Platform Reliability", "slug": "platform-reliability"},
    )
    assert workspace_response.status_code == 201
    workspace = workspace_response.json()
    assert workspace["role"] == "owner"
    workspace_id = workspace["id"]

    repository_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        headers=owner_headers,
        json={
            "full_name": "acme/payments",
            "default_branch": "main",
            "visibility": "private",
        },
    )
    assert repository_response.status_code == 201
    repository = repository_response.json()
    assert repository["provider"] == "development"
    assert repository["data_mode"] == "synthetic"
    assert repository["connection_state"] == "connected"

    invite_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
        json={"email": "friend@example.com", "role": "viewer"},
    )
    assert invite_response.status_code == 201
    invitation = invite_response.json()
    assert invite_response.headers["cache-control"] == "no-store"
    assert invitation["delivery_mode"] == "development_outbox"
    assert invitation["claim_token"] not in invitation["id"]

    listed_invites = client.get(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
    ).json()
    assert len(listed_invites) == 1
    assert "claim_token" not in listed_invites[0]

    with client.app.state.database.session_factory() as session:
        stored = session.scalar(
            select(Invitation).where(Invitation.id == invitation["id"])
        )
        assert stored is not None
        assert stored.token_hash != invitation["claim_token"]

    friend_headers, _ = development_session(
        client, "friend@example.com", "Friend"
    )
    accept_response = client.post(
        "/api/v1/invitations/accept",
        headers=friend_headers,
        json={"token": invitation["claim_token"]},
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["role"] == "viewer"

    friend_workspaces = client.get(
        "/api/v1/workspaces", headers=friend_headers
    ).json()
    assert [item["id"] for item in friend_workspaces] == [workspace_id]
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        headers=friend_headers,
    ).status_code == 200
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        headers=friend_headers,
        json={"full_name": "acme/forbidden", "default_branch": "main"},
    ).status_code == 403
    assert client.post(
        "/api/v1/invitations/accept",
        headers=friend_headers,
        json={"token": invitation["claim_token"]},
    ).json()["code"] == "invalid_invitation"

    audit_events = client.get(
        f"/api/v1/workspaces/{workspace_id}/audit-events",
        headers=owner_headers,
    )
    assert audit_events.status_code == 200
    actions = {event["action"] for event in audit_events.json()}
    assert {
        "workspace.created",
        "repository.connected",
        "invitation.created",
        "invitation.accepted",
    }.issubset(actions)


def test_smtp_invitation_is_durably_queued_without_exposing_a_claim_token(
    tmp_path,
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'smtp-invite.db').as_posix()}",
        smtp_host="smtp.example",
        smtp_from_email="no-reply@deployguard.example",
        invitation_token_secret="i" * 32,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as smtp_client:
        owner_headers, _ = development_session(smtp_client)
        workspace_response = smtp_client.post(
            "/api/v1/workspaces",
            headers=owner_headers,
            json={"name": "SMTP workspace", "slug": "smtp-workspace"},
        )
        assert workspace_response.status_code == 201
        workspace_id = workspace_response.json()["id"]

        response = smtp_client.post(
            f"/api/v1/workspaces/{workspace_id}/invitations",
            headers=owner_headers,
            json={"email": "friend@example.com", "role": "viewer"},
        )
        assert response.status_code == 201
        invitation = response.json()
        assert invitation["delivery_mode"] == "smtp"
        assert invitation["delivery_status"] == "queued"
        assert "claim_token" not in invitation
        assert "accept_path" not in invitation

        with smtp_client.app.state.database.session_factory() as session:
            job = session.scalar(select(BackgroundJob))
            assert job is not None
            assert job.workspace_id == workspace_id
            assert job.payload == {
                "schema_version": 1,
                "invitation_id": invitation["id"],
            }


def test_tenant_isolation_and_invitation_email_binding(
    client: TestClient,
) -> None:
    owner_headers, _ = development_session(client, "a@example.com", "A")
    other_headers, _ = development_session(client, "b@example.com", "B")
    workspace = client.post(
        "/api/v1/workspaces",
        headers=owner_headers,
        json={"name": "A workspace", "slug": "a-workspace"},
    ).json()

    assert client.get(
        f"/api/v1/workspaces/{workspace['id']}/repositories",
        headers=other_headers,
    ).status_code == 404

    invitation = client.post(
        f"/api/v1/workspaces/{workspace['id']}/invitations",
        headers=owner_headers,
        json={"email": "expected@example.com", "role": "responder"},
    ).json()
    wrong_account = client.post(
        "/api/v1/invitations/accept",
        headers=other_headers,
        json={"token": invitation["claim_token"]},
    )
    assert wrong_account.status_code == 400
    assert wrong_account.json()["code"] == "invalid_invitation"


def test_connected_mode_rejects_development_fixture_repository(
    client: TestClient,
) -> None:
    client.app.state.settings.seed_synthetic_data = False
    owner_headers, _ = development_session(
        client, "connected@example.com", "Connected"
    )
    workspace = client.post(
        "/api/v1/workspaces",
        headers=owner_headers,
        json={"name": "Connected workspace", "slug": "connected-workspace"},
    ).json()

    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/repositories",
        headers=owner_headers,
        json={
            "full_name": "acme/should-not-be-a-fixture",
            "default_branch": "main",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "synthetic_repository_disabled"
