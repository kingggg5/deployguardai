import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_metrics_endpoint_is_low_cardinality_and_prometheus_compatible(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200

    metrics_response = client.get("/api/v1/metrics")
    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith(
        "text/plain;"
    )
    body = metrics_response.text
    assert "# TYPE deployguard_http_requests_total counter" in body
    assert re.search(
        r'deployguard_http_requests_total\{method="GET"\} [1-9][0-9]*',
        body,
    )
    assert "request_id" not in body
    assert "path=" not in body


def test_metrics_track_rate_limit_and_body_rejection(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'metrics-guard.db').as_posix()}",
        seed_synthetic_data=True,
        max_request_body_bytes=1_024,
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as guarded:
        first = guarded.post(
            "/api/v1/auth/development-session",
            json={"email": "metrics@example.com", "display_name": "Metrics"},
        )
        assert first.status_code == 200
        second = guarded.post(
            "/api/v1/auth/development-session",
            json={"email": "metrics@example.com", "display_name": "Metrics"},
        )
        assert second.status_code == 429
        oversized = guarded.post(
            "/api/v1/telemetry/events",
            content=b"x" * 1_025,
            headers={"content-type": "application/json"},
        )
        assert oversized.status_code == 413

        body = guarded.get("/api/v1/metrics").text
        assert 'reason="rate_limit_exceeded"' in body
        assert 'reason="request_body_too_large"' in body
