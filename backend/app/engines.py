from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Any


RISK_WEIGHTS: dict[str, float] = {
    "change_size": 0.25,
    "service_scope": 0.20,
    "change_type": 0.20,
    "test_confidence": 0.15,
    "operational_history": 0.10,
    "safety_readiness": 0.10,
}

FLAG_RISK: dict[str, int] = {
    "database-migration": 96,
    "schema-change": 92,
    "retry-policy": 90,
    "auth-change": 86,
    "api-contract": 78,
    "config-change": 68,
    "dependency-upgrade": 58,
    "feature-flag": 42,
    "docs-only": 8,
}

EVIDENCE_TYPE_RELIABILITY: dict[str, float] = {
    "trace": 1.00,
    "metric": 0.95,
    "deployment": 0.92,
    "config": 0.90,
    "log": 0.85,
    "topology": 0.75,
    "human": 0.72,
}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _tier_number(value: object) -> int:
    text = str(value).lower().replace("tier", "").strip(" -_")
    try:
        return int(text)
    except ValueError:
        return 3


def calculate_change_risk(
    *,
    files_changed: int,
    lines_added: int,
    lines_deleted: int,
    changed_services: Sequence[str],
    flags: Sequence[str],
    test_coverage: float,
    rollback_ready: bool,
    observability_score: float,
    previous_failures: int,
    service_tiers: Mapping[str, object] | None = None,
    evidence_prefix: str = "analysis",
) -> dict[str, Any]:
    """Return a bounded, explainable risk ledger with fixed public weights."""

    coverage = clamp(test_coverage, 0.0, 1.0)
    observability = clamp(observability_score, 0.0, 1.0)
    total_lines = max(0, lines_added) + max(0, lines_deleted)
    size_score = round(clamp(max(0, files_changed) * 3 + total_lines / 12, 0, 100))

    tier_map = service_tiers or {}
    tier_bonus_by_number = {1: 25, 2: 12, 3: 4}
    highest_tier_bonus = max(
        (
            tier_bonus_by_number.get(_tier_number(tier_map.get(service)), 4)
            for service in changed_services
        ),
        default=0,
    )
    scope_score = round(
        clamp(
            len(set(changed_services)) * 18
            + max(0, len(set(changed_services)) - 1) * 8
            + highest_tier_bonus,
            0,
            100,
        )
    )

    normalized_flags = [flag.lower() for flag in flags]
    flag_values = [FLAG_RISK.get(flag, 48) for flag in normalized_flags]
    type_score = round(
        clamp(
            (max(flag_values) if flag_values else 20)
            + max(0, len(set(normalized_flags)) - 1) * 4,
            0,
            100,
        )
    )
    test_score = round((1.0 - coverage) * 100)
    history_score = round(clamp(max(0, previous_failures) * 25, 0, 100))
    safety_score = round(
        clamp(
            (0 if rollback_ready else 65) + (1.0 - observability) * 35,
            0,
            100,
        )
    )

    dimension_values = {
        "change_size": size_score,
        "service_scope": scope_score,
        "change_type": type_score,
        "test_confidence": test_score,
        "operational_history": history_score,
        "safety_readiness": safety_score,
    }
    labels = {
        "change_size": "Change size",
        "service_scope": "Service scope",
        "change_type": "Change type",
        "test_confidence": "Test confidence gap",
        "operational_history": "Operational history",
        "safety_readiness": "Safety readiness gap",
    }
    reasons = {
        "change_size": (
            f"{files_changed} files and {total_lines} changed lines increase review surface."
        ),
        "service_scope": (
            f"{len(set(changed_services))} services are directly changed; criticality is included."
        ),
        "change_type": (
            "Flags carry fixed risk priors: "
            + (", ".join(normalized_flags) if normalized_flags else "no elevated flags")
            + "."
        ),
        "test_confidence": f"Reported test coverage is {coverage:.0%}.",
        "operational_history": (
            f"{max(0, previous_failures)} related previous failures were reported."
        ),
        "safety_readiness": (
            f"Rollback readiness is {'available' if rollback_ready else 'missing'}; "
            f"observability is {observability:.0%}."
        ),
    }
    evidence_suffixes = {
        "change_size": "diff",
        "service_scope": "topology",
        "change_type": "flags",
        "test_confidence": "tests",
        "operational_history": "history",
        "safety_readiness": "readiness",
    }

    dimensions = [
        {
            "key": key,
            "label": labels[key],
            "score": score,
            "weight": RISK_WEIGHTS[key],
            "reason": reasons[key],
            "evidence_ids": [f"{evidence_prefix}-{evidence_suffixes[key]}"],
        }
        for key, score in dimension_values.items()
    ]
    overall_score = round(
        clamp(
            sum(
                dimension_values[key] * weight
                for key, weight in RISK_WEIGHTS.items()
            ),
            0,
            100,
        )
    )
    if overall_score < 25:
        level = "low"
    elif overall_score < 50:
        level = "moderate"
    elif overall_score < 70:
        level = "high"
    else:
        level = "critical"

    recommendations: list[str] = []
    if type_score >= 70:
        recommendations.append(
            "Require an owner review for the elevated change type before deployment."
        )
    if test_score >= 35:
        recommendations.append(
            "Add targeted tests for the changed paths before promoting the deployment."
        )
    if scope_score >= 60:
        recommendations.append(
            "Use a staged rollout and watch directly dependent services."
        )
    if not rollback_ready:
        recommendations.append(
            "Prepare and verify a rollback procedure before deployment."
        )
    if observability < 0.7:
        recommendations.append(
            "Add telemetry for the changed services before rollout."
        )
    if not recommendations:
        recommendations.append(
            "Proceed with the normal review path and monitor deployment guardrails."
        )

    data_quality = round(
        clamp(
            0.55
            + observability * 0.20
            + coverage * 0.15
            + (0.10 if changed_services else 0.0),
            0,
            1,
        ),
        2,
    )
    return {
        "overall_score": overall_score,
        "level": level,
        "data_quality": data_quality,
        "dimensions": dimensions,
        "recommendations": recommendations,
    }


def calculate_blast_radius(
    *,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    changed_services: Sequence[str],
    evidence_prefix: str = "topology",
    max_hops: int = 4,
    decay: float = 0.72,
) -> dict[str, Any]:
    """Traverse active impact-direction edges using BFS and confidence decay."""

    nodes_by_id = {str(node["id"]): dict(node) for node in nodes}
    for service_id in changed_services:
        nodes_by_id.setdefault(
            service_id,
            {
                "id": service_id,
                "label": service_id.replace("-", " ").title(),
                "kind": "service",
                "team": "Unassigned",
                "tier": "tier-3",
                "health": "unknown",
            },
        )

    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_edge in edges:
        edge = dict(raw_edge)
        edge.setdefault("relation", "runtime-dependency")
        edge.setdefault("confidence", 1.0)
        edge.setdefault("active", True)
        if edge["active"]:
            adjacency[str(edge["source"])].append(edge)
    for outgoing in adjacency.values():
        outgoing.sort(key=lambda item: (str(item["target"]), str(item["relation"])))

    distance: dict[str, int] = {}
    path_confidence: dict[str, float] = {}
    origin: dict[str, str] = {}
    queue: deque[str] = deque()
    for service_id in sorted(set(changed_services)):
        distance[service_id] = 0
        path_confidence[service_id] = 1.0
        origin[service_id] = service_id
        queue.append(service_id)

    while queue:
        source = queue.popleft()
        if distance[source] >= max_hops:
            continue
        for edge in adjacency.get(source, []):
            target = str(edge["target"])
            if target not in nodes_by_id:
                continue
            next_distance = distance[source] + 1
            next_confidence = path_confidence[source] * clamp(
                float(edge["confidence"]), 0.0, 1.0
            )
            is_better = (
                target not in distance
                or next_distance < distance[target]
                or (
                    next_distance == distance[target]
                    and next_confidence > path_confidence[target]
                )
            )
            if is_better:
                distance[target] = next_distance
                path_confidence[target] = next_confidence
                origin[target] = origin[source]
                queue.append(target)

    tier_factors = {1: 1.0, 2: 0.92, 3: 0.82}
    health_factors = {
        "critical": 1.20,
        "degraded": 1.10,
        "healthy": 1.00,
        "unknown": 0.90,
    }
    result_nodes: list[dict[str, Any]] = []
    for node_id in sorted(distance, key=lambda item: (distance[item], item)):
        node = nodes_by_id[node_id]
        if distance[node_id] == 0:
            impact_score = 100
        else:
            tier_factor = tier_factors.get(_tier_number(node.get("tier")), 0.82)
            health_factor = health_factors.get(
                str(node.get("health", "unknown")).lower(), 0.90
            )
            impact_score = round(
                clamp(
                    100
                    * (decay ** distance[node_id])
                    * path_confidence[node_id]
                    * tier_factor
                    * health_factor,
                    0,
                    100,
                )
            )
        result_nodes.append(
            {
                "id": node_id,
                "label": str(node.get("label", node_id)),
                "kind": str(node.get("kind", "service")),
                "team": str(node.get("team", "Unassigned")),
                "tier": str(node.get("tier", "tier-3")),
                "health": str(node.get("health", "unknown")),
                "impact_score": impact_score,
                "hop_distance": distance[node_id],
                "evidence_ids": [
                    f"{evidence_prefix}-{origin[node_id]}-{node_id}"
                ],
            }
        )

    result_edges = [
        {
            "source": str(edge["source"]),
            "target": str(edge["target"]),
            "relation": str(edge.get("relation", "runtime-dependency")),
            "confidence": round(
                clamp(float(edge.get("confidence", 1.0)), 0.0, 1.0), 2
            ),
            "active": bool(edge.get("active", True)),
        }
        for edge in edges
        if bool(edge.get("active", True))
        and str(edge["source"]) in distance
        and str(edge["target"]) in distance
        and distance[str(edge["target"])] == distance[str(edge["source"])] + 1
    ]
    result_edges.sort(key=lambda edge: (edge["source"], edge["target"]))
    return {"nodes": result_nodes, "edges": result_edges}


def rank_hypotheses(
    *,
    evidence: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Rank RCA candidates from explicit supporting and contradicting evidence."""

    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        supporting = [
            item for item in evidence if candidate_id in item.get("supports", [])
        ]
        contradicting = [
            item
            for item in evidence
            if candidate_id in item.get("contradicts", [])
        ]

        def strength(item: Mapping[str, Any]) -> float:
            quality = clamp(float(item.get("quality", 0.5)), 0.0, 1.0)
            reliability = EVIDENCE_TYPE_RELIABILITY.get(
                str(item.get("type", "")).lower(), 0.70
            )
            return quality * reliability

        support_strength = sum(strength(item) for item in supporting)
        counter_strength = sum(strength(item) for item in contradicting)
        distinct_types = len({str(item.get("type")) for item in supporting})
        prior = clamp(float(candidate.get("prior", 0.5)), 0.0, 1.0)
        score = round(
            clamp(
                prior * 25
                + min(55, support_strength * 16)
                - min(45, counter_strength * 28)
                + min(10, distinct_types * 3)
                + min(6, len(supporting) * 1.5),
                0,
                100,
            )
        )
        average_quality = (
            sum(float(item.get("quality", 0.5)) for item in supporting)
            / len(supporting)
            if supporting
            else 0.0
        )
        confidence = round(
            clamp(
                0.15
                + 0.55 * (score / 100)
                + 0.15 * min(1.0, len(supporting) / 2)
                + 0.10 * average_quality
                - 0.12 * min(1.0, counter_strength),
                0.05,
                0.98,
            ),
            2,
        )
        if supporting:
            reasoning = (
                f"{len(supporting)} evidence item(s) support this cause"
                f" across {distinct_types} evidence type(s)"
            )
        else:
            reasoning = "No direct supporting evidence is currently available"
        if contradicting:
            reasoning += (
                f"; {len(contradicting)} counter-evidence item(s) reduce confidence."
            )
        else:
            reasoning += "; no counter-evidence is currently recorded."

        ranked.append(
            {
                "id": candidate_id,
                "rank": 0,
                "cause_service": str(candidate["cause_service"]),
                "cause": str(candidate["cause"]),
                "confidence": confidence,
                "score": score,
                "evidence_ids": [str(item["id"]) for item in supporting],
                "counter_evidence_ids": [
                    str(item["id"]) for item in contradicting
                ],
                "reasoning": reasoning,
                "next_step": str(candidate["next_step"]),
                "status": str(candidate.get("status", "unreviewed")),
            }
        )

    ranked.sort(key=lambda item: (-item["score"], item["id"]))
    selected = ranked[: max(0, limit)]
    for index, item in enumerate(selected, start=1):
        item["rank"] = index
    return selected
