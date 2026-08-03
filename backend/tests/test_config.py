from app.config import Settings
from pydantic import ValidationError
import pytest


def test_comma_separated_cors_origins_are_read_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:4300,http://localhost:4300",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://127.0.0.1:4300",
        "http://localhost:4300",
    ]


def test_postgresql_database_url_uses_psycopg_driver() -> None:
    settings = Settings(
        database_url="postgresql://deployguard:secret@db/deployguard",
        _env_file=None,
    )

    assert settings.database_url == (
        "postgresql+psycopg://deployguard:secret@db/deployguard"
    )


def test_synthetic_data_is_opt_in_and_rejected_in_production() -> None:
    settings = Settings(_env_file=None)
    assert settings.seed_synthetic_data is False

    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            auth_provider="oidc",
            oidc_issuer="https://identity.example",
            oidc_audience="deployguard-api",
            oidc_jwks_url="https://identity.example/.well-known/jwks.json",
            seed_synthetic_data=True,
            _env_file=None,
        )


def _production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "database_url": (
            "postgresql+psycopg://deployguard:secret@db/deployguard"
        ),
        "auth_provider": "oidc",
        "oidc_issuer": "https://identity.example",
        "oidc_audience": "deployguard-api",
        "oidc_jwks_url": "https://identity.example/.well-known/jwks.json",
        "frontend_public_url": "https://deployguard.example",
        "cors_origins": ["https://deployguard.example"],
        "run_migrations_on_startup": False,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_requires_postgresql_https_and_explicit_cors() -> None:
    assert _production_settings().environment == "production"

    for overrides in (
        {"database_url": "sqlite:///deployguard.db"},
        {"frontend_public_url": "http://deployguard.example"},
        {"cors_origins": ["https://*"]},
        {"oidc_issuer": "http://identity.example"},
        {"run_migrations_on_startup": True},
    ):
        with pytest.raises(ValidationError):
            _production_settings(**overrides)


def test_provider_configuration_fails_closed_when_partial_or_weak() -> None:
    with pytest.raises(ValidationError, match="GitHub App configuration"):
        _production_settings(github_app_id="123")
    with pytest.raises(ValidationError, match="GITHUB_CHECKS_ENABLED"):
        _production_settings(github_checks_enabled=True)
    with pytest.raises(ValidationError, match="GITHUB_WEBHOOK_SECRET"):
        _production_settings(github_webhook_secret="too-short")
    with pytest.raises(ValidationError, match="SMTP configuration"):
        _production_settings(smtp_host="smtp.example")
    with pytest.raises(ValidationError, match="SMTP_USE_TLS"):
        _production_settings(
            smtp_host="smtp.example",
            smtp_from_email="deployguard@example.com",
            smtp_use_tls=False,
        )
