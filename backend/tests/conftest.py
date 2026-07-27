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
        cors_origins=[
            "http://127.0.0.1:4300",
            "http://localhost:4300",
        ],
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client

