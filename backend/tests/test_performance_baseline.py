from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BASELINE_SCRIPT = REPOSITORY_ROOT / "scripts" / "performance_baseline.py"
RESULT_SCHEMA = REPOSITORY_ROOT / "scripts" / "performance" / "result-schema-v1.json"


def _load_baseline_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "deployguard_performance_baseline",
        BASELINE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load performance baseline")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = _load_baseline_module()


def test_performance_result_schema_covers_required_measurements() -> None:
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))

    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["properties"]["schema"]["const"] == BASELINE.RESULT_SCHEMA_VERSION
    required = set(schema["properties"]["measurements"]["required"])
    assert required == {
        "risk_engine",
        "graph_engine_by_size",
        "api_startup_to_liveness",
        "expired_job_recovery",
        "python_traced_memory",
    }


def test_test_profile_produces_complete_honest_measurement() -> None:
    result = BASELINE.run_baseline("test")
    measurements = result["measurements"]

    assert result["schema"] == BASELINE.RESULT_SCHEMA_VERSION
    assert result["profile"] == "test"
    assert measurements["risk_engine"]["iterations"] == 5
    assert len(measurements["risk_engine"]["output_sha256"]) == 64
    assert measurements["graph_engine_by_size"][0]["input_nodes"] == 10
    assert measurements["graph_engine_by_size"][0]["reached_nodes"] == 10
    assert measurements["api_startup_to_liveness"]["successful_samples"] == 1
    assert measurements["expired_job_recovery"]["stale_jobs"] == 5
    assert measurements["expired_job_recovery"]["recovered_jobs"] == 5
    assert measurements["expired_job_recovery"]["queued_after_recovery"] == 5
    assert measurements["python_traced_memory"]["peak_bytes"] > 0
    assert any("not a production SLO" in item for item in result["limitations"])

