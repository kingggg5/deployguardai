import hashlib
import hmac

from fastapi.testclient import TestClient


def _signature(body: bytes) -> str:
    return "sha256=" + hmac.new(
        b"test-github-secret",
        body,
        hashlib.sha256,
    ).hexdigest()


def test_github_webhook_requires_delivery_identity(
    client: TestClient,
) -> None:
    body = b"{}"

    response = client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-Hub-Signature-256": _signature(body),
            "Content-Type": "application/json",
        },
        content=body,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_github_event_header"


def test_github_webhook_rejects_invalid_json(client: TestClient) -> None:
    body = b"{"

    response = client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "invalid-json-delivery",
            "X-Hub-Signature-256": _signature(body),
            "Content-Type": "application/json",
        },
        content=body,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_github_webhook_json"


def test_github_webhook_enforces_body_limit(client: TestClient) -> None:
    body = b'{"padding":"' + (b"x" * 1_100) + b'"}'
    client.app.state.settings.github_webhook_max_body_bytes = 1_024

    response = client.post(
        "/api/v1/webhooks/github",
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "oversized-delivery",
            "X-Hub-Signature-256": _signature(body),
            "Content-Type": "application/json",
        },
        content=body,
    )

    assert response.status_code == 413
    assert response.json()["code"] == "github_webhook_body_too_large"
