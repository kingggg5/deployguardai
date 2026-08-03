from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.engines import (
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    RCA_SCORING_POLICY_VERSION,
    RISK_SCORING_POLICY_VERSION,
    calculate_blast_radius,
    calculate_change_risk,
    rank_hypotheses,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPOSITORY_ROOT / "scripts" / "evaluation" / "golden-corpus-v1.json"
ENGINE_FUNCTIONS = {
    "calculate_change_risk": calculate_change_risk,
    "calculate_blast_radius": calculate_blast_radius,
    "rank_hypotheses": rank_hypotheses,
}


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _summary(engine: str, output: Any) -> dict[str, object]:
    if engine == "calculate_change_risk":
        return {
            key: output[key]
            for key in ("overall_score", "level", "data_quality")
        }
    if engine == "calculate_blast_radius":
        return {
            "node_ids": [node["id"] for node in output["nodes"]],
            "edge_count": len(output["edges"]),
            "max_hop": max(
                (node["hop_distance"] for node in output["nodes"]),
                default=0,
            ),
        }
    return {
        "ranked_ids": [hypothesis["id"] for hypothesis in output],
        "scores": [hypothesis["score"] for hypothesis in output],
    }


def _corpus() -> dict[str, Any]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def test_golden_corpus_is_versioned_and_tracks_engine_contract() -> None:
    corpus = _corpus()

    assert corpus["schema"] == "deployguard-golden-corpus/v1"
    assert corpus["data_mode"] == "synthetic"
    assert corpus["engine_contract"] == {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "risk_scoring_policy_version": RISK_SCORING_POLICY_VERSION,
        "graph_version": GRAPH_VERSION,
        "rca_scoring_policy_version": RCA_SCORING_POLICY_VERSION,
    }
    case_ids = [case["id"] for case in corpus["cases"]]
    assert len(case_ids) == len(set(case_ids))
    assert {case["engine"] for case in corpus["cases"]} == set(ENGINE_FUNCTIONS)
    assert all(case["expected_sha256"] != "PENDING" for case in corpus["cases"])


@pytest.mark.parametrize("case", _corpus()["cases"], ids=lambda case: case["id"])
def test_engine_output_matches_versioned_golden_case(case: dict[str, Any]) -> None:
    output = ENGINE_FUNCTIONS[case["engine"]](**case["input"])

    assert _summary(case["engine"], output) == case["expected_summary"]
    assert _canonical_sha256(output) == case["expected_sha256"]

