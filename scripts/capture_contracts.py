"""Capture or verify the versioned OpenAPI and representative HTTP contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


CONTRACT_VERSION = "v1"
CONTRACT_DIRECTORY = REPOSITORY_ROOT / "scripts" / "contracts" / CONTRACT_VERSION
OPENAPI_FIXTURE = CONTRACT_DIRECTORY / "openapi.json"
RESPONSE_FIXTURE = CONTRACT_DIRECTORY / "representative-responses.json"
_RESPONSE_CASES = (
    ("health", "GET", "/api/v1/health"),
    ("seeded-change", "GET", "/api/v1/changes/chg-checkout-timeout"),
    ("seeded-incident", "GET", "/api/v1/incidents/inc-checkout-latency"),
    ("overview", "GET", "/api/v1/overview"),
    ("not-found-error", "GET", "/api/v1/changes/contract-fixture-not-found"),
)


def _settings(database_url: str = "sqlite:///:memory:") -> Settings:
    return Settings(
        app_name="DeployGuard AI",
        environment="test",
        database_url=database_url,
        seed_synthetic_data=False,
        auth_provider="development",
        rate_limit_requests=1_000,
        otel_traces_endpoint="",
        _env_file=None,
    )


def capture_openapi() -> dict[str, Any]:
    """Return the complete generated OpenAPI document without starting the DB."""

    return create_app(_settings()).openapi()


def _normalize_response(name: str, body: Any) -> Any:
    # Overview generation time is intentionally dynamic.  All stored domain
    # timestamps remain exact so fixture drift still catches contract changes.
    if name == "overview" and isinstance(body, dict):
        body = dict(body)
        body["generated_at"] = "<generated-at>"
    return body


def capture_representative_responses() -> dict[str, Any]:
    """Exercise seeded synthetic read contracts in an isolated SQLite DB."""

    with TemporaryDirectory(prefix="deployguard-contract-") as directory:
        database_path = Path(directory) / "contracts.db"
        settings = _settings(f"sqlite:///{database_path.as_posix()}")
        settings.seed_synthetic_data = True
        responses: list[dict[str, Any]] = []
        with TestClient(create_app(settings)) as client:
            for name, method, path in _RESPONSE_CASES:
                response = client.request(method, path)
                responses.append(
                    {
                        "name": name,
                        "request": {"method": method, "path": path},
                        "status_code": response.status_code,
                        "content_type": response.headers.get("content-type"),
                        "body": _normalize_response(name, response.json()),
                    }
                )
    return {
        "schema": "deployguard-representative-api-contract/v1",
        "contract_version": CONTRACT_VERSION,
        "data_mode": "synthetic",
        "normalizations": {
            "overview.generated_at": "<generated-at>",
        },
        "responses": responses,
    }


def _encoded(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def write_contracts() -> None:
    CONTRACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    OPENAPI_FIXTURE.write_text(_encoded(capture_openapi()), encoding="utf-8")
    RESPONSE_FIXTURE.write_text(
        _encoded(capture_representative_responses()),
        encoding="utf-8",
    )


def check_contracts() -> list[str]:
    expected = {
        OPENAPI_FIXTURE: capture_openapi(),
        RESPONSE_FIXTURE: capture_representative_responses(),
    }
    drifted: list[str] = []
    for path, current in expected.items():
        if not path.exists() or path.read_text(encoding="utf-8") != _encoded(current):
            drifted.append(str(path.relative_to(REPOSITORY_ROOT)))
    return drifted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="replace fixtures")
    action.add_argument("--check", action="store_true", help="fail on contract drift")
    args = parser.parse_args()

    if args.write:
        write_contracts()
        print(f"Wrote contracts to {CONTRACT_DIRECTORY.relative_to(REPOSITORY_ROOT)}")
        return
    drifted = check_contracts()
    if drifted:
        print("Contract drift detected: " + ", ".join(drifted))
        raise SystemExit(1)
    print(f"Contract fixtures match {CONTRACT_VERSION}")


if __name__ == "__main__":
    main()

