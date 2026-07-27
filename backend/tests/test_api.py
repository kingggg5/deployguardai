from fastapi.testclient import TestClient


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
    assert all(item["data_mode"] == "synthetic" for item in scenarios.json())


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
    assert bad_hypothesis.status_code == 404
    assert bad_hypothesis.json()["code"] == "hypothesis_not_found"


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
    assert dora.json()["total_deployments"] >= 3

    webhook = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "del-8812"},
        json={"pull_request": {"title": "Update retry limit", "changed_files": 4, "additions": 40, "deletions": 10}},
    )
    assert webhook.status_code == 200
    assert webhook.json()["status"] == "accepted"

    telemetry = client.post(
        "/api/v1/telemetry/events",
        json={"source": "loki", "type": "log", "service_id": "checkout-api", "summary": "High latency detected"},
    )
    assert telemetry.status_code == 201
    assert telemetry.json()["status"] == "ok"

    llm = client.post("/api/v1/incidents/inc-checkout-latency/synthesize-llm")
    assert llm.status_code == 200
    assert llm.json()["unsupported_claims_count"] == 0

    export_md = client.get("/api/v1/incidents/inc-checkout-latency/export-markdown")
    assert export_md.status_code == 200
    assert "# Incident Post-Mortem" in export_md.text


def test_ml_model_prediction() -> None:
    from app.ml_trainer import PRRiskMLModel
    model = PRRiskMLModel()
    score = model.predict_risk_score({"files_changed": 15, "lines_added": 400, "changed_services": ["checkout-api", "payment-adapter"]})
    assert 0 <= score <= 100
