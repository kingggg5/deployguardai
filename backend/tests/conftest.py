from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "deployguard-test.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        seed_synthetic_data=True,
        cors_origins=[
            "http://127.0.0.1:4300",
            "http://localhost:4300",
        ],
        github_webhook_secret="test-github-secret",
        telemetry_ingest_token="test-telemetry-token",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
