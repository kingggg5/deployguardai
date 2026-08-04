import hashlib
import hmac
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.engines import (
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    GRAPH_VERSION_NOT_APPLICABLE,
    RCA_SCORING_POLICY_VERSION,
    RISK_SCORING_POLICY_VERSION,
)
from app.main import create_app
from app.models import (
    AuditEvent,
    LEGACY_REPOSITORY_ID,
    LEGACY_WORKSPACE_ID,
)


ANALYZE_PAYLOAD = {
    "title": "Tighten checkout timeout and retry policy",
    "repository": "acme/checkout-platform",
    "author": "narin",
    "files_changed": 11,
    "lines_added": 286,
    "lines_deleted": 74,
    "changed_services": ["checkout-api", "payment-adapter"],
    "flags": ["config-change", "retry-policy"],
    "test_coverage": 0.72,
    "rollback_ready": True,
    "observability_score": 0.84,
    "previous_failures": 1,
}


def test_health_overview_and_seeded_lists(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    overview = client.get("/api/v1/overview")
    scenarios = client.get("/api/v1/scenarios")
    changes = client.get("/api/v1/changes")
    incidents = client.get("/api/v1/incidents")

    assert health.status_code == 200
    assert health.json()["database"] == "ready"
    assert overview.status_code == 200
    assert overview.json()["active_scenario_id"] == "checkout-retry-storm"
    assert overview.json()["data_mode"] == "synthetic"
    assert len(scenarios.json()) == 3
    assert sum(item["is_active"] for item in scenarios.json()) == 1
    assert len(changes.json()) == 3
    assert len(incidents.json()) == 3
    assert all(item["repository"] for item in scenarios.json())
    assert all(item["data_mode"] == "synthetic" for item in scenarios.json())
    expected_change_versions = {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "scoring_policy_version": RISK_SCORING_POLICY_VERSION,
        "graph_version": GRAPH_VERSION,
    }
    expected_incident_versions = {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "scoring_policy_version": RCA_SCORING_POLICY_VERSION,
        "graph_version": GRAPH_VERSION_NOT_APPLICABLE,
    }
    assert all(
        {key: item[key] for key in expected_change_versions}
        == expected_change_versions
        for item in changes.json()
    )
    assert all(
        {key: item[key] for key in expected_incident_versions}
        == expected_incident_versions
        for item in incidents.json()
    )


def test_health_reports_connected_for_fresh_runtime(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'connected.db').as_posix()}",
        seed_synthetic_data=False,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as fresh_client:
        health = fresh_client.get("/api/v1/health")

    assert health.status_code == 200
    assert health.json()["data_mode"] == "connected"


def test_scenario_activation_returns_selected_overview(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/scenarios/catalog-cache-regression/activate"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_scenario_id"] == "catalog-cache-regression"
    assert payload["active_change"]["id"] == "chg-catalog-cache-key"
    scenarios = client.get("/api/v1/scenarios").json()
    active = [item["id"] for item in scenarios if item["is_active"]]
    assert active == ["catalog-cache-regression"]


def test_analyze_change_persists_bounded_explainable_result(
    client: TestClient,
) -> None:
    first = client.post("/api/v1/changes/analyze", json=ANALYZE_PAYLOAD)
    second = client.post("/api/v1/changes/analyze", json=ANALYZE_PAYLOAD)

    assert first.status_code == 201
    assert second.status_code == 201
    payload = first.json()
    assert payload["id"] == second.json()["id"]
    assert payload["workspace_id"] == LEGACY_WORKSPACE_ID
    assert payload["repository_id"] == LEGACY_REPOSITORY_ID
    assert {
        "analysis_schema_version": payload["analysis_schema_version"],
        "engine_version": payload["engine_version"],
        "scoring_policy_version": payload["scoring_policy_version"],
        "graph_version": payload["graph_version"],
    } == {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "scoring_policy_version": RISK_SCORING_POLICY_VERSION,
        "graph_version": GRAPH_VERSION,
    }
    assert 0 <= payload["risk"]["overall_score"] <= 100
    assert len(payload["risk"]["dimensions"]) == 6
    assert payload["risk"]["recommendations"]
    assert payload["blast_radius"]["nodes"]
    assert client.get(f"/api/v1/changes/{payload['id']}").status_code == 200
    assert len(client.get("/api/v1/changes").json()) == 4
    assert (
        client.get("/api/v1/overview").json()["active_change"]["id"]
        == "chg-checkout-timeout"
    )


def test_analysis_version_change_creates_a_new_snapshot(
    client: TestClient, monkeypatch
) -> None:
    from app import services

    first = client.post("/api/v1/changes/analyze", json=ANALYZE_PAYLOAD)
    monkeypatch.setattr(services, "ENGINE_VERSION", "1.0.1-test")
    second = client.post("/api/v1/changes/analyze", json=ANALYZE_PAYLOAD)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["engine_version"] == "1.0.1-test"
    assert client.get(f"/api/v1/changes/{first.json()['id']}").json()[
        "engine_version"
    ] == ENGINE_VERSION


def test_feedback_is_recorded_and_updates_hypothesis_status(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/incidents/inc-checkout-latency/feedback",
        json={
            "hypothesis_id": "hyp-payment-timeout",
            "verdict": "confirmed",
            "note": "Trace replay confirmed timeout before retry fan-out.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    hypothesis = next(
        item
        for item in payload["hypotheses"]
        if item["id"] == "hyp-payment-timeout"
    )
    assert hypothesis["status"] == "confirmed"
    assert payload["feedback"][-1]["verdict"] == "confirmed"
    assert payload["scoring_policy_version"] == RCA_SCORING_POLICY_VERSION
    assert payload["graph_version"] == GRAPH_VERSION_NOT_APPLICABLE
    persisted = client.get(
        "/api/v1/incidents/inc-checkout-latency"
    ).json()
    assert len(persisted["feedback"]) == 1


def test_domain_and_validation_errors(client: TestClient) -> None:
    missing = client.get("/api/v1/changes/not-found")
    invalid = client.post(
        "/api/v1/changes/analyze",
        json={**ANALYZE_PAYLOAD, "test_coverage": 1.4},
    )
    client_selected_engine = client.post(
        "/api/v1/changes/analyze",
        json={**ANALYZE_PAYLOAD, "engine_version": "attacker-selected"},
    )
    bad_hypothesis = client.post(
        "/api/v1/incidents/inc-checkout-latency/feedback",
        json={
            "hypothesis_id": "does-not-exist",
            "verdict": "confirmed",
            "note": "No match.",
        },
    )

    assert missing.status_code == 404
    assert missing.json() == {
        "detail": "Change not found",
        "code": "change_not_found",
    }
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)
    assert client_selected_engine.status_code == 422
    assert bad_hypothesis.status_code == 404
    assert bad_hypothesis.json()["code"] == "hypothesis_not_found"


def test_openapi_requires_persisted_analysis_versions(
    client: TestClient,
) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    version_fields = {
        "analysis_schema_version",
        "engine_version",
        "scoring_policy_version",
        "graph_version",
    }

    for schema_name in ("ChangeDetail", "IncidentDetail"):
        schema = schemas[schema_name]
        assert version_fields <= set(schema["properties"])
        assert version_fields <= set(schema["required"])
    assert version_fields.isdisjoint(
        schemas["AnalyzeChangeRequest"]["properties"]
    )


def test_cors_allows_both_configured_frontend_origins(
    client: TestClient,
) -> None:
    for origin in [
        "http://127.0.0.1:4300",
        "http://localhost:4300",
    ]:
        response = client.options(
            "/api/v1/overview",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_dora_metrics_webhook_telemetry_llm(client: TestClient) -> None:
    dora = client.get("/api/v1/metrics/dora")
    assert dora.status_code == 200
    assert dora.json()["period"] == "Last 30 Days"
    assert dora.json()["total_deployments"] == 3
    assert dora.json()["deployment_frequency_per_week"] == 0.7
    assert dora.json()["change_lead_time_minutes"] == 7.7
    assert dora.json()["change_failure_rate"] == 1.0
    assert dora.json()["mean_time_to_restore_minutes"] == 25.5
    assert dora.json()["deployment_rework_rate"] == 0.333

    webhook_payload = {
        "pull_request": {
            "title": "Update retry limit",
            "changed_files": 4,
            "additions": 40,
            "deletions": 10,
        }
    }
    webhook_body = json.dumps(
        webhook_payload, separators=(",", ":")
    ).encode()
    webhook_signature = "sha256=" + hmac.new(
        b"test-github-secret", webhook_body, hashlib.sha256
    ).hexdigest()
    webhook = client.post(
        "/api/v1/webhooks/github",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "del-8812",
            "X-Hub-Signature-256": webhook_signature,
        },
        content=webhook_body,
    )
    assert webhook.status_code == 200
    assert webhook.json()["status"] == "accepted"

    telemetry = client.post(
        "/api/v1/telemetry/events",
        headers={"Authorization": "Bearer test-telemetry-token"},
        json={"source": "loki", "type": "log", "service_id": "checkout-api", "summary": "High latency detected"},
    )
    assert telemetry.status_code == 201
    assert telemetry.json()["status"] == "ok"

    incident = client.get("/api/v1/incidents/inc-checkout-latency")
    assert incident.status_code == 200
    synthesis = client.post("/api/v1/incidents/inc-checkout-latency/synthesize")
    assert synthesis.status_code == 200
    synthesis_payload = synthesis.json()
    assert synthesis_payload["synthesis_mode"] == "deterministic_evidence_template"
    assert synthesis_payload["model_used"] == "deterministic-evidence-template-v1"
    assert synthesis_payload["citation_coverage"] == 1.0
    assert synthesis_payload["unsupported_claims_count"] == 0
    evidence_ids = {item["id"] for item in incident.json()["evidence"]}
    for statement in [
        *synthesis_payload["summary"],
        *synthesis_payload["uncertainty"],
    ]:
        assert set(statement["evidence_ids"]) <= evidence_ids
    for hypothesis in synthesis_payload["explained_hypotheses"]:
        assert set(hypothesis["explanation"]["evidence_ids"]) <= evidence_ids

    legacy_synthesis = client.post(
        "/api/v1/incidents/inc-checkout-latency/synthesize-llm"
    )
    assert legacy_synthesis.status_code == 200
    assert legacy_synthesis.json()["evidence_bundle_sha256"] == (
        synthesis_payload["evidence_bundle_sha256"]
    )
    session = client.app.state.database.session_factory()
    try:
        synthesis_audits = [
            event
            for event in session.query(AuditEvent)
            .filter(AuditEvent.action == "incident.synthesis.generated")
            .all()
            if event.resource_id == "inc-checkout-latency"
        ]
    finally:
        session.close()
    assert len(synthesis_audits) == 2
    assert all(
        event.event_metadata["evidence_bundle_sha256"]
        == synthesis_payload["evidence_bundle_sha256"]
        for event in synthesis_audits
    )

    export_md = client.get("/api/v1/incidents/inc-checkout-latency/export-markdown")
    assert export_md.status_code == 200
    assert "# Incident Post-Mortem" in export_md.text


def test_external_write_endpoints_are_secure_by_default(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deployguard-secure-defaults.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        cors_origins=["http://127.0.0.1:4300"],
        _env_file=None,
    )

    with TestClient(create_app(settings)) as secure_client:
        webhook = secure_client.post(
            "/api/v1/webhooks/github",
            headers={"X-Hub-Signature-256": "sha256=invalid"},
            json={"pull_request": {"title": "Unsigned change"}},
        )
        assert webhook.status_code == 503
        assert webhook.json()["code"] == "github_webhook_not_configured"

        telemetry = secure_client.post(
            "/api/v1/telemetry/events",
            json={
                "source": "loki",
                "type": "log",
                "service_id": "checkout-api",
                "summary": "Untrusted telemetry",
            },
        )
        assert telemetry.status_code == 503
        assert telemetry.json()["code"] == "telemetry_ingest_not_configured"

        reset = secure_client.post("/api/v1/reset-database")
        assert reset.status_code == 403
        assert reset.json()["code"] == "database_reset_disabled"
