from __future__ import annotations

import random

from app.engines import (
    RISK_WEIGHTS,
    calculate_blast_radius,
    calculate_change_risk,
    rank_hypotheses,
)


SEED = 20260803


def _random_risk_input(rng: random.Random) -> dict[str, object]:
    service_count = rng.randint(0, 8)
    services = [f"service-{index}" for index in range(service_count)]
    flag_pool = [
        "docs-only",
        "feature-flag",
        "dependency-upgrade",
        "config-change",
        "api-contract",
        "auth-change",
        "retry-policy",
        "schema-change",
        "database-migration",
    ]
    return {
        "files_changed": rng.randint(0, 2_000),
        "lines_added": rng.randint(0, 100_000),
        "lines_deleted": rng.randint(0, 100_000),
        "changed_services": services,
        "flags": rng.sample(flag_pool, rng.randint(0, len(flag_pool))),
        "test_coverage": rng.random(),
        "rollback_ready": rng.choice([True, False]),
        "observability_score": rng.random(),
        "previous_failures": rng.randint(0, 20),
        "service_tiers": {
            service: f"tier-{rng.randint(1, 3)}" for service in services
        },
    }


def test_risk_properties_hold_across_seeded_input_space() -> None:
    rng = random.Random(SEED)

    for _ in range(250):
        inputs = _random_risk_input(rng)
        result = calculate_change_risk(**inputs)
        assert result == calculate_change_risk(**inputs)
        assert 0 <= result["overall_score"] <= 100
        assert 0 <= result["data_quality"] <= 1
        assert len(result["dimensions"]) == len(RISK_WEIGHTS)
        assert all(0 <= item["score"] <= 100 for item in result["dimensions"])
        assert sum(item["weight"] for item in result["dimensions"]) == 1.0

        larger = calculate_change_risk(
            **{
                **inputs,
                "files_changed": int(inputs["files_changed"]) + rng.randint(1, 100),
                "lines_added": int(inputs["lines_added"]) + rng.randint(1, 1_000),
            }
        )
        assert larger["overall_score"] >= result["overall_score"]

        less_tested = calculate_change_risk(
            **{
                **inputs,
                "test_coverage": max(0.0, float(inputs["test_coverage"]) - 0.2),
            }
        )
        assert less_tested["overall_score"] >= result["overall_score"]


def test_blast_radius_properties_hold_for_seeded_random_graphs() -> None:
    rng = random.Random(SEED + 1)

    for _ in range(120):
        node_count = rng.randint(1, 40)
        node_ids = [f"service-{index}" for index in range(node_count)]
        nodes = [
            {
                "id": node_id,
                "label": node_id,
                "kind": "service",
                "team": f"team-{index % 4}",
                "tier": f"tier-{rng.randint(1, 3)}",
                "health": rng.choice(["healthy", "degraded", "critical", "unknown"]),
            }
            for index, node_id in enumerate(node_ids)
        ]
        edges = [
            {
                "source": rng.choice(node_ids),
                "target": rng.choice(node_ids),
                "relation": "runtime-dependency",
                "confidence": rng.uniform(-0.5, 1.5),
                "active": rng.random() > 0.15,
            }
            for _ in range(rng.randint(0, node_count * 4))
        ]
        max_hops = rng.randint(0, 8)
        inputs = {
            "nodes": nodes,
            "edges": edges,
            "changed_services": [node_ids[0]],
            "max_hops": max_hops,
            "decay": rng.random(),
        }
        result = calculate_blast_radius(**inputs)

        assert result == calculate_blast_radius(**inputs)
        reached_ids = [node["id"] for node in result["nodes"]]
        assert len(reached_ids) == len(set(reached_ids))
        assert set(reached_ids) <= set(node_ids)
        assert all(0 <= node["impact_score"] <= 100 for node in result["nodes"])
        assert all(0 <= node["hop_distance"] <= max_hops for node in result["nodes"])
        assert all(0 <= edge["confidence"] <= 1 for edge in result["edges"])
        assert all(edge["active"] for edge in result["edges"])


def test_rca_properties_hold_across_seeded_evidence_bundles() -> None:
    rng = random.Random(SEED + 2)

    for iteration in range(180):
        candidate_count = rng.randint(1, 12)
        candidate_ids = [f"h-{iteration}-{index}" for index in range(candidate_count)]
        candidates = [
            {
                "id": candidate_id,
                "cause_service": f"service-{index}",
                "cause": f"Cause {index}",
                "prior": rng.random(),
                "next_step": f"Inspect service {index}.",
            }
            for index, candidate_id in enumerate(candidate_ids)
        ]
        evidence = []
        for evidence_index in range(rng.randint(0, 30)):
            supports: list[str] = []
            contradicts: list[str] = []
            for candidate_id in candidate_ids:
                disposition = rng.randrange(5)
                if disposition == 0:
                    supports.append(candidate_id)
                elif disposition == 1:
                    contradicts.append(candidate_id)
            evidence.append(
                {
                    "id": f"e-{iteration}-{evidence_index}",
                    "type": rng.choice(
                        ["trace", "metric", "deployment", "config", "log", "human"]
                    ),
                    "quality": rng.random(),
                    "supports": supports,
                    "contradicts": contradicts,
                }
            )
        limit = rng.randint(0, candidate_count)
        result = rank_hypotheses(
            evidence=evidence,
            candidates=candidates,
            limit=limit,
        )
        reordered = rank_hypotheses(
            evidence=evidence,
            candidates=list(reversed(candidates)),
            limit=limit,
        )

        assert result == reordered
        assert len(result) == limit
        assert [item["rank"] for item in result] == list(range(1, limit + 1))
        assert len({item["id"] for item in result}) == len(result)
        assert all(item["id"] in candidate_ids for item in result)
        assert all(0 <= item["score"] <= 100 for item in result)
        assert all(0.05 <= item["confidence"] <= 0.98 for item in result)
        evidence_ids = {item["id"] for item in evidence}
        assert all(
            set(item["evidence_ids"] + item["counter_evidence_ids"])
            <= evidence_ids
            for item in result
        )


def test_more_counter_evidence_never_improves_single_candidate_rank() -> None:
    candidate = {
        "id": "candidate",
        "cause_service": "checkout-api",
        "cause": "Candidate cause",
        "prior": 0.5,
        "next_step": "Inspect the evidence.",
    }
    support = {
        "id": "support",
        "type": "trace",
        "quality": 1.0,
        "supports": ["candidate"],
        "contradicts": [],
    }
    previous = rank_hypotheses(
        evidence=[support], candidates=[candidate], limit=1
    )[0]

    for index, quality in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
        current = rank_hypotheses(
            evidence=[
                support,
                {
                    "id": f"counter-{index}",
                    "type": "trace",
                    "quality": quality,
                    "supports": [],
                    "contradicts": ["candidate"],
                },
            ],
            candidates=[candidate],
            limit=1,
        )[0]
        assert current["score"] <= previous["score"]
        assert current["confidence"] <= previous["confidence"]
        previous = current

