import pytest

from app.engines import (
    RISK_WEIGHTS,
    calculate_blast_radius,
    calculate_change_risk,
    rank_hypotheses,
)


def test_risk_dimensions_have_stable_weights_and_bounded_scores() -> None:
    result = calculate_change_risk(
        files_changed=10_000,
        lines_added=1_000_000,
        lines_deleted=1_000_000,
        changed_services=["checkout-api", "payment-adapter"],
        flags=["database-migration", "retry-policy"],
        test_coverage=-1,
        rollback_ready=False,
        observability_score=2,
        previous_failures=100,
        service_tiers={"checkout-api": "tier-1"},
    )

    assert sum(RISK_WEIGHTS.values()) == pytest.approx(1.0)
    assert 0 <= result["overall_score"] <= 100
    assert 0 <= result["data_quality"] <= 1
    assert {item["key"] for item in result["dimensions"]} == set(RISK_WEIGHTS)
    assert all(0 <= item["score"] <= 100 for item in result["dimensions"])
    assert all(item["evidence_ids"] for item in result["dimensions"])


def test_risk_is_deterministic_and_safer_inputs_score_lower() -> None:
    base = {
        "files_changed": 5,
        "lines_added": 80,
        "lines_deleted": 20,
        "changed_services": ["catalog-api"],
        "flags": ["config-change"],
        "service_tiers": {"catalog-api": "tier-2"},
    }
    safe = calculate_change_risk(
        **base,
        test_coverage=0.98,
        rollback_ready=True,
        observability_score=0.98,
        previous_failures=0,
    )
    risky = calculate_change_risk(
        **base,
        test_coverage=0.25,
        rollback_ready=False,
        observability_score=0.2,
        previous_failures=3,
    )

    assert safe == calculate_change_risk(
        **base,
        test_coverage=0.98,
        rollback_ready=True,
        observability_score=0.98,
        previous_failures=0,
    )
    assert safe["overall_score"] < risky["overall_score"]


def test_unknown_change_evidence_stays_explicit_and_conservative() -> None:
    result = calculate_change_risk(
        files_changed=3,
        lines_added=20,
        lines_deleted=4,
        changed_services=["checkout-api"],
        flags=["provider-metadata-only"],
        test_coverage=None,
        rollback_ready=None,
        observability_score=None,
        previous_failures=None,
    )

    dimensions = {item["key"]: item for item in result["dimensions"]}
    assert dimensions["test_confidence"]["score"] == 50
    assert "No test coverage evidence" in dimensions["test_confidence"]["reason"]
    assert "unknown" in dimensions["safety_readiness"]["reason"]
    assert result["data_quality"] < 0.5
    assert any("SHA-matched test evidence" in item for item in result["recommendations"])


def test_blast_radius_uses_bfs_decay_and_handles_cycles() -> None:
    nodes = [
        {
            "id": item,
            "label": item.upper(),
            "kind": "service",
            "team": "Core",
            "tier": "tier-1",
            "health": "healthy",
        }
        for item in ["a", "b", "c", "d"]
    ]
    edges = [
        {"source": "a", "target": "b", "confidence": 1, "active": True},
        {"source": "b", "target": "c", "confidence": 1, "active": True},
        {"source": "c", "target": "a", "confidence": 1, "active": True},
        {"source": "a", "target": "d", "confidence": 1, "active": False},
    ]

    result = calculate_blast_radius(
        nodes=nodes, edges=edges, changed_services=["a"], decay=0.5
    )
    by_id = {node["id"]: node for node in result["nodes"]}

    assert set(by_id) == {"a", "b", "c"}
    assert by_id["a"]["hop_distance"] == 0
    assert by_id["b"]["hop_distance"] == 1
    assert by_id["c"]["hop_distance"] == 2
    assert by_id["a"]["impact_score"] > by_id["b"]["impact_score"]
    assert by_id["b"]["impact_score"] > by_id["c"]["impact_score"]
    assert all(0 <= node["impact_score"] <= 100 for node in result["nodes"])


def test_rca_returns_top_three_with_counter_evidence_penalty() -> None:
    evidence = [
        {
            "id": "trace-1",
            "type": "trace",
            "quality": 1,
            "supports": ["h1"],
            "contradicts": [],
        },
        {
            "id": "metric-1",
            "type": "metric",
            "quality": 0.9,
            "supports": ["h1", "h2"],
            "contradicts": [],
        },
        {
            "id": "metric-2",
            "type": "metric",
            "quality": 1,
            "supports": [],
            "contradicts": ["h2"],
        },
    ]
    candidates = [
        {
            "id": f"h{index}",
            "cause_service": f"service-{index}",
            "cause": f"Cause {index}",
            "prior": 0.5,
            "next_step": "Inspect evidence.",
        }
        for index in range(1, 4)
    ]

    result = rank_hypotheses(evidence=evidence, candidates=candidates)

    assert len(result) == 3
    assert [item["rank"] for item in result] == [1, 2, 3]
    assert result[0]["id"] == "h1"
    h2 = next(item for item in result if item["id"] == "h2")
    assert h2["counter_evidence_ids"] == ["metric-2"]
    assert all(0 <= item["score"] <= 100 for item in result)
    assert all(0 <= item["confidence"] <= 1 for item in result)
