from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.oidc import OIDCVerifier
from app.config import Settings
from app.errors import DomainError
from app.main import create_app
from app.models import LEGACY_REPOSITORY_ID, LEGACY_WORKSPACE_ID


def _development_session(
    client: TestClient, email: str
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/development-session",
        json={"email": email, "display_name": email.split("@")[0]},
    )
    assert response.status_code == 200
    return {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }


def test_oidc_verifier_validates_signature_issuer_audience_and_claims() -> None:
    settings = Settings(
        auth_provider="oidc",
        oidc_issuer="https://identity.example",
        oidc_audience="deployguard-api",
        oidc_jwks_url="https://identity.example/.well-known/jwks.json",
        _env_file=None,
    )
    verifier = OIDCVerifier(settings)
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )
    verifier._jwks = SimpleNamespace(  # type: ignore[assignment]
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(
            key=private_key.public_key()
        )
    )
    now = datetime.now(UTC)
    claims = {
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "sub": "user-123",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "email": "user@example.com",
        "email_verified": True,
        "name": "Example User",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")

    identity = verifier.verify(token)

    assert identity.subject == "user-123"
    assert identity.email == "user@example.com"
    wrong_audience = jwt.encode(
        {**claims, "aud": "another-api"},
        private_key,
        algorithm="RS256",
    )
    with pytest.raises(DomainError) as raised:
        verifier.verify(wrong_audience)
    assert raised.value.code == "invalid_access_token"


def test_production_rejects_development_auth() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            auth_provider="development",
            _env_file=None,
        )


def test_user_context_prevents_cross_workspace_legacy_reads(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/overview").status_code == 200
    owner_headers = _development_session(
        client, "owner@deployguard.local"
    )
    owner_context = client.get(
        "/api/v1/me/context", headers=owner_headers
    )
    assert owner_context.json() == {
        "workspace_id": LEGACY_WORKSPACE_ID,
        "repository_id": LEGACY_REPOSITORY_ID,
        "scenario_id": "checkout-retry-storm",
    }

    other_headers = _development_session(client, "other@example.com")
    other_workspace = client.post(
        "/api/v1/workspaces",
        headers=other_headers,
        json={"name": "Other", "slug": "other"},
    ).json()
    assert client.get(
        "/api/v1/changes", headers=other_headers
    ).json() == []

    forbidden_selection = client.put(
        "/api/v1/me/context",
        headers=owner_headers,
        json={
            "workspace_id": other_workspace["id"],
            "repository_id": None,
            "scenario_id": None,
        },
    )
    assert forbidden_selection.status_code == 404
    assert forbidden_selection.json()["code"] == "workspace_not_found"
    assert len(
        client.get("/api/v1/changes", headers=owner_headers).json()
    ) == 3


def test_oidc_routes_require_bearer_credentials(tmp_path) -> None:
    settings = Settings(
        environment="test",
        auth_provider="oidc",
        oidc_issuer="https://identity.example",
        oidc_audience="deployguard-api",
        oidc_jwks_url="https://identity.example/.well-known/jwks.json",
        database_url=f"sqlite:///{(tmp_path / 'oidc.db').as_posix()}",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/workspaces")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
