from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = REPOSITORY_ROOT / "scripts" / "capture_contracts.py"


def _load_capture_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "deployguard_contract_capture",
        CAPTURE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load contract capture script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CAPTURE = _load_capture_module()


def _fixture(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_complete_openapi_document_matches_versioned_fixture() -> None:
    captured = CAPTURE.capture_openapi()
    expected = _fixture(CAPTURE.OPENAPI_FIXTURE)

    assert captured == expected
    assert captured["openapi"].startswith("3.")
    assert len(captured["paths"]) >= 40
    assert "ChangeDetail" in captured["components"]["schemas"]
    assert "IncidentDetail" in captured["components"]["schemas"]


def test_representative_http_responses_match_versioned_fixture() -> None:
    captured = CAPTURE.capture_representative_responses()
    expected = _fixture(CAPTURE.RESPONSE_FIXTURE)

    assert captured == expected
    assert captured["data_mode"] == "synthetic"
    assert {item["name"] for item in captured["responses"]} == {
        "health",
        "seeded-change",
        "seeded-incident",
        "overview",
        "not-found-error",
    }
    assert all(
        item["body"].get("data_mode") == "synthetic"
        for item in captured["responses"]
        if item["name"] != "not-found-error"
    )

