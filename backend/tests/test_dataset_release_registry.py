from __future__ import annotations

from fastapi.testclient import TestClient


def test_dataset_release_registry_is_redaction_checked_and_revocable(
    client: TestClient,
) -> None:
    session = client.post(
        "/api/v1/auth/development-session",
        json={"email": "dataset-admin@example.com", "display_name": "Dataset Admin"},
    )
    headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
    workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Dataset Registry", "slug": "dataset-registry"},
    ).json()
    workspace_id = workspace["id"]
    payload = {
        "release_version": "eval-2026-08-08",
        "purpose": "evaluation",
        "status": "ready_for_review",
        "bundle_sha256": "a" * 64,
        "source_snapshot_count": 1,
        "manifest": {
            "dataset_card": "deployguard-eval",
            "records": [
                {"example_id": "case-1", "split": "train", "content": {"x": 1}}
            ],
        },
    }
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/dataset/releases",
        headers=headers,
        json=payload,
    )
    assert created.status_code == 201
    release_id = created.json()["id"]
    assert created.json()["status"] == "ready_for_review"

    secret = dict(payload)
    secret["release_version"] = "secret-case"
    secret["bundle_sha256"] = "b" * 64
    secret["manifest"] = {"records": [{"content": {"api_key": "do-not-export"}}]}
    rejected = client.post(
        f"/api/v1/workspaces/{workspace_id}/dataset/releases",
        headers=headers,
        json=secret,
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "dataset_release_redaction_required"

    revoked = client.post(
        f"/api/v1/workspaces/{workspace_id}/dataset/releases/{release_id}/revoke",
        headers=headers,
        json={"reason": "Consent was withdrawn by the workspace owner."},
    )
    assert revoked.status_code == 201
    assert len(revoked.json()["tombstone_sha256"]) == 64
    listed = client.get(
        f"/api/v1/workspaces/{workspace_id}/dataset/releases",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "revoked"
