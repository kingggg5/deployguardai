import pytest

from app.errors import DomainError
from app.github_client import GitHubAppClient


def _client() -> GitHubAppClient:
    return GitHubAppClient(
        app_id="1",
        private_key="unused-in-unit-test",
        api_url="https://api.github.test",
        api_version="2026-03-10",
    )


def test_create_check_run_uses_installation_token_and_typed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        client,
        "_installation_token",
        lambda installation_id: (
            "installation-token"
            if installation_id == "123"
            else pytest.fail("unexpected installation")
        ),
    )

    def fake_request(
        method: str,
        path: str,
        *,
        token: str,
        body: dict | None = None,
    ) -> dict:
        captured.update(
            method=method,
            path=path,
            token=token,
            body=body,
        )
        return {"id": 987, "status": "completed", "conclusion": "neutral"}

    monkeypatch.setattr(client, "_request", fake_request)

    result = client.create_check_run(
        installation_id="123",
        repository_full_name="acme/checkout-api",
        head_sha="a" * 40,
        external_id="change-42",
        conclusion="neutral",
        title="Review recommended · risk 58/100",
        summary="Deterministic evidence summary.",
        details_url="https://deployguard.example/?view=change_risk",
    )

    assert result["id"] == 987
    assert captured["method"] == "POST"
    assert captured["path"] == "/repos/acme/checkout-api/check-runs"
    assert captured["token"] == "installation-token"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["name"] == "DeployGuard change risk"
    assert body["status"] == "completed"
    assert body["conclusion"] == "neutral"
    assert body["external_id"] == "change-42"
    assert body["details_url"] == "https://deployguard.example/?view=change_risk"


@pytest.mark.parametrize(
    ("repository", "conclusion", "head_sha"),
    [
        ("missing-owner", "success", "a" * 40),
        ("acme/nested/repository", "success", "a" * 40),
        ("acme/checkout", "unsupported", "a" * 40),
        ("acme/checkout", "success", "not-a-commit"),
    ],
)
def test_create_check_run_rejects_invalid_inputs(
    repository: str,
    conclusion: str,
    head_sha: str,
) -> None:
    client = _client()

    with pytest.raises(DomainError) as raised:
        client.create_check_run(
            installation_id="123",
            repository_full_name=repository,
            head_sha=head_sha,
            external_id="change-42",
            conclusion=conclusion,
            title="Risk result",
            summary="Summary",
        )

    assert raised.value.code == "github_check_input_invalid"


def test_update_and_recover_check_run_use_stable_external_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    requests: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(
        client,
        "_installation_token",
        lambda _installation_id: "installation-token",
    )

    def fake_request(
        method: str,
        path: str,
        *,
        token: str,
        body: dict | None = None,
    ) -> dict:
        assert token == "installation-token"
        requests.append((method, path, body))
        if method == "GET":
            return {
                "check_runs": [
                    {"id": 987, "external_id": "another-publication"},
                    {"id": 654, "external_id": "publication-42"},
                ]
            }
        return {"id": 654, "status": "completed", "conclusion": "success"}

    monkeypatch.setattr(client, "_request", fake_request)
    recovered = client.find_check_run(
        installation_id="123",
        repository_full_name="acme/checkout-api",
        head_sha="b" * 40,
        external_id="publication-42",
    )
    assert recovered == {"id": 654, "external_id": "publication-42"}
    assert requests[0][0] == "GET"
    assert "/commits/" + "b" * 40 + "/check-runs" in requests[0][1]
    assert "filter=all" in requests[0][1]

    updated = client.update_check_run(
        installation_id="123",
        repository_full_name="acme/checkout-api",
        provider_check_id="654",
        head_sha="b" * 40,
        external_id="publication-42",
        conclusion="success",
        title="Normal review",
        summary="Updated deterministic evidence.",
        details_url="https://deployguard.example/?change=change-42",
    )
    assert updated["id"] == 654
    method, path, body = requests[1]
    assert method == "PATCH"
    assert path == "/repos/acme/checkout-api/check-runs/654"
    assert body is not None
    assert "head_sha" not in body
    assert body["external_id"] == "publication-42"
