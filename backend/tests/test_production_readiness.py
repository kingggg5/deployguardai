from scripts.production_readiness import (
    OPERATOR_ATTESTATIONS,
    assess_production_readiness,
)

from test_config import _production_settings


def _configured_settings():
    return _production_settings(
        github_app_id="12345",
        github_app_slug="deployguard",
        github_app_private_key="-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----",
        github_webhook_secret="w" * 32,
        github_checks_enabled=True,
        smtp_host="smtp.example",
        smtp_from_email="deployguard@example.com",
        invitation_token_secret="i" * 32,
        telemetry_ingest_token="t" * 32,
        otel_traces_endpoint="http://collector:4318/v1/traces",
    )


def test_production_readiness_requires_external_attestations() -> None:
    report = assess_production_readiness(_configured_settings(), {})

    assert report["ready"] is False
    assert all(item["passed"] for item in report["checks"])
    assert not any(item["passed"] for item in report["operator_attestations"])


def test_production_readiness_passes_only_when_every_gate_is_explicit() -> None:
    environment = {name: "true" for name in OPERATOR_ATTESTATIONS}

    report = assess_production_readiness(
        _configured_settings(),
        environment,
    )

    assert report["ready"] is True
    assert all(
        item["passed"]
        for item in report["checks"] + report["operator_attestations"]
    )
