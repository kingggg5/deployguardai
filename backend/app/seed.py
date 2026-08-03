from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .engines import (
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    GRAPH_VERSION_NOT_APPLICABLE,
    RCA_SCORING_POLICY_VERSION,
    RISK_SCORING_POLICY_VERSION,
    calculate_blast_radius,
    calculate_change_risk,
    rank_hypotheses,
)
from .models import ChangeRecord, IncidentRecord, Scenario


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


SCENARIO_SPECS: list[dict[str, Any]] = [
    {
        "id": "checkout-retry-storm",
        "name": "Checkout retry storm",
        "description": (
            "A timeout and retry-policy change increases payment traffic and "
            "degrades checkout."
        ),
        "change": {
            "id": "chg-checkout-timeout",
            "title": "Tighten checkout timeout and retry policy",
            "repository": "acme/checkout-platform",
            "author": "narin",
            "commit_sha": "8f2d9b17c4a1",
            "branch": "release/checkout-resilience",
            "created_at": "2026-07-24T09:02:00Z",
            "deployment_status": "deployed",
            "deployment_environment": "production",
            "changed_services": ["checkout-api", "payment-adapter"],
            "files_changed": 18,
            "lines_added": 462,
            "lines_deleted": 137,
            "flags": ["config-change", "retry-policy"],
            "test_coverage": 0.68,
            "rollback_ready": True,
            "observability_score": 0.88,
            "previous_failures": 2,
        },
        "graph": {
            "nodes": [
                {
                    "id": "payment-adapter",
                    "label": "Payment Adapter",
                    "kind": "service",
                    "team": "Payments",
                    "tier": "tier-1",
                    "health": "degraded",
                },
                {
                    "id": "checkout-api",
                    "label": "Checkout API",
                    "kind": "service",
                    "team": "Commerce",
                    "tier": "tier-1",
                    "health": "critical",
                },
                {
                    "id": "web-checkout",
                    "label": "Web Checkout",
                    "kind": "experience",
                    "team": "Storefront",
                    "tier": "tier-1",
                    "health": "degraded",
                },
                {
                    "id": "order-service",
                    "label": "Order Service",
                    "kind": "service",
                    "team": "Commerce",
                    "tier": "tier-1",
                    "health": "healthy",
                },
                {
                    "id": "receipt-worker",
                    "label": "Receipt Worker",
                    "kind": "worker",
                    "team": "Commerce",
                    "tier": "tier-2",
                    "health": "healthy",
                },
            ],
            "edges": [
                {
                    "source": "payment-adapter",
                    "target": "checkout-api",
                    "relation": "upstream-dependency",
                    "confidence": 0.98,
                    "active": True,
                },
                {
                    "source": "checkout-api",
                    "target": "web-checkout",
                    "relation": "serves",
                    "confidence": 0.99,
                    "active": True,
                },
                {
                    "source": "checkout-api",
                    "target": "order-service",
                    "relation": "creates-orders",
                    "confidence": 0.94,
                    "active": True,
                },
                {
                    "source": "order-service",
                    "target": "receipt-worker",
                    "relation": "emits-events",
                    "confidence": 0.88,
                    "active": True,
                },
            ],
        },
        "incident": {
            "id": "inc-checkout-latency",
            "title": "Checkout latency and payment retries elevated",
            "severity": "SEV-1",
            "status": "investigating",
            "started_at": "2026-07-24T09:18:00Z",
            "resolved_at": None,
            "affected_services": [
                "checkout-api",
                "payment-adapter",
                "web-checkout",
            ],
            "summary": (
                "Checkout p95 latency rose after the retry-policy deployment. "
                "Evidence points to an adapter timeout before retry fan-out."
            ),
            "timeline": [
                {
                    "id": "tl-checkout-deploy",
                    "timestamp": "2026-07-24T09:10:00Z",
                    "type": "deployment",
                    "title": "Change deployed",
                    "detail": "Checkout API and payment adapter rollout reached 100%.",
                    "service_id": "checkout-api",
                },
                {
                    "id": "tl-checkout-alert",
                    "timestamp": "2026-07-24T09:18:00Z",
                    "type": "alert",
                    "title": "Latency SLO breached",
                    "detail": "Checkout p95 exceeded 2.5 seconds for five minutes.",
                    "service_id": "checkout-api",
                },
                {
                    "id": "tl-checkout-trace",
                    "timestamp": "2026-07-24T09:23:00Z",
                    "type": "investigation",
                    "title": "Trace sample isolated timeout",
                    "detail": "Payment adapter timed out before duplicate retry spans.",
                    "service_id": "payment-adapter",
                },
            ],
            "evidence": [
                {
                    "id": "ev-checkout-deploy",
                    "type": "deployment",
                    "source": "deployment-controller",
                    "timestamp": "2026-07-24T09:10:00Z",
                    "summary": "Symptoms began eight minutes after the correlated rollout.",
                    "value": "8m",
                    "quality": 0.96,
                    "service_id": "checkout-api",
                    "supports": ["hyp-payment-timeout", "hyp-retry-fanout"],
                    "contradicts": [],
                },
                {
                    "id": "ev-payment-trace",
                    "type": "trace",
                    "source": "otel-traces",
                    "timestamp": "2026-07-24T09:23:00Z",
                    "summary": "Adapter timeout precedes three retry child spans.",
                    "value": "timeout=800ms,retries=3",
                    "quality": 0.98,
                    "service_id": "payment-adapter",
                    "supports": ["hyp-payment-timeout", "hyp-retry-fanout"],
                    "contradicts": ["hyp-checkout-code"],
                },
                {
                    "id": "ev-retry-metric",
                    "type": "metric",
                    "source": "prometheus",
                    "timestamp": "2026-07-24T09:20:00Z",
                    "summary": "Payment retry rate increased 4.7 times baseline.",
                    "value": 4.7,
                    "quality": 0.94,
                    "service_id": "payment-adapter",
                    "supports": ["hyp-retry-fanout", "hyp-payment-timeout"],
                    "contradicts": [],
                },
                {
                    "id": "ev-provider-success",
                    "type": "metric",
                    "source": "provider-status-probe",
                    "timestamp": "2026-07-24T09:21:00Z",
                    "summary": "Direct provider success rate remained within baseline.",
                    "value": 0.997,
                    "quality": 0.91,
                    "service_id": "payment-adapter",
                    "supports": [],
                    "contradicts": ["hyp-provider-outage"],
                },
                {
                    "id": "ev-timeout-config",
                    "type": "config",
                    "source": "git-diff",
                    "timestamp": "2026-07-24T09:02:00Z",
                    "summary": "Adapter timeout was reduced from 1800ms to 800ms.",
                    "value": "1800ms -> 800ms",
                    "quality": 1.0,
                    "service_id": "payment-adapter",
                    "supports": ["hyp-payment-timeout"],
                    "contradicts": [],
                },
            ],
            "candidates": [
                {
                    "id": "hyp-payment-timeout",
                    "cause_service": "payment-adapter",
                    "cause": "Payment adapter timeout is below normal provider latency.",
                    "prior": 0.72,
                    "next_step": "Replay representative traces with the previous timeout.",
                },
                {
                    "id": "hyp-retry-fanout",
                    "cause_service": "payment-adapter",
                    "cause": "The new retry policy amplifies requests under timeout.",
                    "prior": 0.66,
                    "next_step": "Disable retries in a canary and compare request volume.",
                },
                {
                    "id": "hyp-provider-outage",
                    "cause_service": "payment-gateway",
                    "cause": "The external payment provider is unavailable.",
                    "prior": 0.45,
                    "next_step": "Compare direct provider probes by region.",
                },
                {
                    "id": "hyp-checkout-code",
                    "cause_service": "checkout-api",
                    "cause": "A checkout application regression increases latency.",
                    "prior": 0.38,
                    "next_step": "Profile checkout handlers against the previous build.",
                },
            ],
        },
    },
    {
        "id": "catalog-cache-regression",
        "name": "Catalog cache regression",
        "description": (
            "A cache-key schema change lowers hit rate and increases catalog latency."
        ),
        "change": {
            "id": "chg-catalog-cache-key",
            "title": "Version catalog cache keys",
            "repository": "acme/catalog",
            "author": "mali",
            "commit_sha": "25c1a77e2d90",
            "branch": "main",
            "created_at": "2026-07-22T13:40:00Z",
            "deployment_status": "rolled_back",
            "deployment_environment": "production",
            "changed_services": ["catalog-cache", "catalog-api"],
            "files_changed": 9,
            "lines_added": 211,
            "lines_deleted": 82,
            "flags": ["schema-change", "config-change"],
            "test_coverage": 0.81,
            "rollback_ready": True,
            "observability_score": 0.92,
            "previous_failures": 1,
        },
        "graph": {
            "nodes": [
                {
                    "id": "catalog-cache",
                    "label": "Catalog Cache",
                    "kind": "datastore",
                    "team": "Catalog",
                    "tier": "tier-1",
                    "health": "healthy",
                },
                {
                    "id": "catalog-api",
                    "label": "Catalog API",
                    "kind": "service",
                    "team": "Catalog",
                    "tier": "tier-1",
                    "health": "healthy",
                },
                {
                    "id": "storefront",
                    "label": "Storefront",
                    "kind": "experience",
                    "team": "Storefront",
                    "tier": "tier-1",
                    "health": "healthy",
                },
                {
                    "id": "search-api",
                    "label": "Search API",
                    "kind": "service",
                    "team": "Discovery",
                    "tier": "tier-2",
                    "health": "healthy",
                },
            ],
            "edges": [
                {
                    "source": "catalog-cache",
                    "target": "catalog-api",
                    "relation": "read-path",
                    "confidence": 0.99,
                    "active": True,
                },
                {
                    "source": "catalog-api",
                    "target": "storefront",
                    "relation": "serves",
                    "confidence": 0.97,
                    "active": True,
                },
                {
                    "source": "catalog-api",
                    "target": "search-api",
                    "relation": "feeds",
                    "confidence": 0.89,
                    "active": True,
                },
            ],
        },
        "incident": {
            "id": "inc-catalog-cache-miss",
            "title": "Catalog cache miss rate elevated",
            "severity": "SEV-2",
            "status": "resolved",
            "started_at": "2026-07-22T13:52:00Z",
            "resolved_at": "2026-07-22T14:31:00Z",
            "affected_services": ["catalog-cache", "catalog-api", "storefront"],
            "summary": (
                "A cache-key version mismatch reduced hit rate. Rolling back the "
                "change restored baseline latency."
            ),
            "timeline": [
                {
                    "id": "tl-catalog-deploy",
                    "timestamp": "2026-07-22T13:45:00Z",
                    "type": "deployment",
                    "title": "Catalog release deployed",
                    "detail": "Cache and API changes reached production.",
                    "service_id": "catalog-api",
                },
                {
                    "id": "tl-catalog-alert",
                    "timestamp": "2026-07-22T13:52:00Z",
                    "type": "alert",
                    "title": "Cache hit-rate alert",
                    "detail": "Hit rate fell below the 80% guardrail.",
                    "service_id": "catalog-cache",
                },
                {
                    "id": "tl-catalog-resolved",
                    "timestamp": "2026-07-22T14:31:00Z",
                    "type": "resolution",
                    "title": "Rollback completed",
                    "detail": "Hit rate and latency returned to baseline.",
                    "service_id": "catalog-cache",
                },
            ],
            "evidence": [
                {
                    "id": "ev-cache-hit-rate",
                    "type": "metric",
                    "source": "prometheus",
                    "timestamp": "2026-07-22T13:52:00Z",
                    "summary": "Cache hit rate fell from 94% to 41%.",
                    "value": 0.41,
                    "quality": 0.98,
                    "service_id": "catalog-cache",
                    "supports": ["hyp-cache-key-mismatch"],
                    "contradicts": [],
                },
                {
                    "id": "ev-cache-key-log",
                    "type": "log",
                    "source": "loki",
                    "timestamp": "2026-07-22T13:55:00Z",
                    "summary": "Readers requested v2 keys while writers emitted v1 keys.",
                    "value": "reader=v2,writer=v1",
                    "quality": 0.95,
                    "service_id": "catalog-cache",
                    "supports": ["hyp-cache-key-mismatch"],
                    "contradicts": ["hyp-database-load"],
                },
                {
                    "id": "ev-rollback-recovery",
                    "type": "deployment",
                    "source": "deployment-controller",
                    "timestamp": "2026-07-22T14:31:00Z",
                    "summary": "Metrics recovered within four minutes of rollback.",
                    "value": "4m",
                    "quality": 0.97,
                    "service_id": "catalog-api",
                    "supports": ["hyp-cache-key-mismatch", "hyp-cache-warmup"],
                    "contradicts": ["hyp-network-loss"],
                },
                {
                    "id": "ev-network-baseline",
                    "type": "metric",
                    "source": "network-monitor",
                    "timestamp": "2026-07-22T14:02:00Z",
                    "summary": "Packet loss remained at baseline.",
                    "value": 0.001,
                    "quality": 0.90,
                    "service_id": "catalog-api",
                    "supports": [],
                    "contradicts": ["hyp-network-loss"],
                },
            ],
            "candidates": [
                {
                    "id": "hyp-cache-key-mismatch",
                    "cause_service": "catalog-cache",
                    "cause": "Reader and writer cache-key versions do not match.",
                    "prior": 0.74,
                    "next_step": "Verify key generation for every writer and reader.",
                    "status": "confirmed",
                },
                {
                    "id": "hyp-cache-warmup",
                    "cause_service": "catalog-cache",
                    "cause": "A cold cache temporarily increases origin traffic.",
                    "prior": 0.48,
                    "next_step": "Compare recovery curve with a controlled cache flush.",
                    "status": "rejected",
                },
                {
                    "id": "hyp-network-loss",
                    "cause_service": "catalog-api",
                    "cause": "Network packet loss increases cache latency.",
                    "prior": 0.34,
                    "next_step": "Inspect zone-level retransmission metrics.",
                    "status": "rejected",
                },
                {
                    "id": "hyp-database-load",
                    "cause_service": "catalog-db",
                    "cause": "Database saturation slows cache miss resolution.",
                    "prior": 0.37,
                    "next_step": "Compare database wait time with cache miss volume.",
                },
            ],
        },
    },
    {
        "id": "auth-key-rotation",
        "name": "Guarded auth key rotation",
        "description": (
            "A staged signing-key rotation shows bounded transient latency and "
            "healthy guardrails."
        ),
        "change": {
            "id": "chg-auth-key-rotation",
            "title": "Rotate identity signing keys with dual-read support",
            "repository": "acme/identity",
            "author": "anong",
            "commit_sha": "b71d40c64f08",
            "branch": "release/key-rotation",
            "created_at": "2026-07-20T07:15:00Z",
            "deployment_status": "deployed",
            "deployment_environment": "production",
            "changed_services": ["identity-provider"],
            "files_changed": 7,
            "lines_added": 184,
            "lines_deleted": 39,
            "flags": ["auth-change", "feature-flag"],
            "test_coverage": 0.94,
            "rollback_ready": True,
            "observability_score": 0.97,
            "previous_failures": 0,
        },
        "graph": {
            "nodes": [
                {
                    "id": "identity-provider",
                    "label": "Identity Provider",
                    "kind": "service",
                    "team": "Identity",
                    "tier": "tier-1",
                    "health": "healthy",
                },
                {
                    "id": "api-gateway",
                    "label": "API Gateway",
                    "kind": "gateway",
                    "team": "Platform",
                    "tier": "tier-1",
                    "health": "healthy",
                },
                {
                    "id": "merchant-console",
                    "label": "Merchant Console",
                    "kind": "experience",
                    "team": "Merchant",
                    "tier": "tier-2",
                    "health": "healthy",
                },
                {
                    "id": "checkout-api",
                    "label": "Checkout API",
                    "kind": "service",
                    "team": "Commerce",
                    "tier": "tier-1",
                    "health": "healthy",
                },
            ],
            "edges": [
                {
                    "source": "identity-provider",
                    "target": "api-gateway",
                    "relation": "token-verification",
                    "confidence": 0.99,
                    "active": True,
                },
                {
                    "source": "api-gateway",
                    "target": "merchant-console",
                    "relation": "authenticates",
                    "confidence": 0.96,
                    "active": True,
                },
                {
                    "source": "api-gateway",
                    "target": "checkout-api",
                    "relation": "authenticates",
                    "confidence": 0.98,
                    "active": True,
                },
            ],
        },
        "incident": {
            "id": "inc-auth-latency",
            "title": "Transient token verification latency",
            "severity": "SEV-3",
            "status": "resolved",
            "started_at": "2026-07-20T07:29:00Z",
            "resolved_at": "2026-07-20T07:41:00Z",
            "affected_services": ["identity-provider", "api-gateway"],
            "summary": (
                "Dual-key verification briefly increased p95 latency without "
                "errors. The canary stabilized within the rollout guardrail."
            ),
            "timeline": [
                {
                    "id": "tl-auth-canary",
                    "timestamp": "2026-07-20T07:25:00Z",
                    "type": "deployment",
                    "title": "Key rotation canary started",
                    "detail": "Five percent of verification traffic used dual-read.",
                    "service_id": "identity-provider",
                },
                {
                    "id": "tl-auth-latency",
                    "timestamp": "2026-07-20T07:29:00Z",
                    "type": "alert",
                    "title": "Latency guardrail observed",
                    "detail": "Verification p95 increased by 34ms without error growth.",
                    "service_id": "identity-provider",
                },
                {
                    "id": "tl-auth-stable",
                    "timestamp": "2026-07-20T07:41:00Z",
                    "type": "resolution",
                    "title": "Canary stabilized",
                    "detail": "Latency returned inside the rollout guardrail.",
                    "service_id": "identity-provider",
                },
            ],
            "evidence": [
                {
                    "id": "ev-auth-latency",
                    "type": "metric",
                    "source": "prometheus",
                    "timestamp": "2026-07-20T07:29:00Z",
                    "summary": "Verification p95 increased by 34ms.",
                    "value": "34ms",
                    "quality": 0.96,
                    "service_id": "identity-provider",
                    "supports": ["hyp-dual-key-cpu"],
                    "contradicts": [],
                },
                {
                    "id": "ev-auth-errors",
                    "type": "metric",
                    "source": "prometheus",
                    "timestamp": "2026-07-20T07:32:00Z",
                    "summary": "Authentication error rate remained at baseline.",
                    "value": 0.0004,
                    "quality": 0.98,
                    "service_id": "api-gateway",
                    "supports": [],
                    "contradicts": ["hyp-key-rejection", "hyp-gateway-failure"],
                },
                {
                    "id": "ev-auth-trace",
                    "type": "trace",
                    "source": "otel-traces",
                    "timestamp": "2026-07-20T07:34:00Z",
                    "summary": "Extra latency is isolated to dual signature verification.",
                    "value": "verify_secondary_key",
                    "quality": 0.97,
                    "service_id": "identity-provider",
                    "supports": ["hyp-dual-key-cpu"],
                    "contradicts": ["hyp-gateway-failure"],
                },
                {
                    "id": "ev-auth-stabilized",
                    "type": "deployment",
                    "source": "rollout-controller",
                    "timestamp": "2026-07-20T07:41:00Z",
                    "summary": "Latency stabilized while the canary remained active.",
                    "value": "guardrail-pass",
                    "quality": 0.93,
                    "service_id": "identity-provider",
                    "supports": ["hyp-dual-key-cpu"],
                    "contradicts": ["hyp-key-rejection"],
                },
            ],
            "candidates": [
                {
                    "id": "hyp-dual-key-cpu",
                    "cause_service": "identity-provider",
                    "cause": "Dual signature verification adds bounded CPU latency.",
                    "prior": 0.65,
                    "next_step": "Compare CPU profiles before and during dual verification.",
                    "status": "confirmed",
                },
                {
                    "id": "hyp-key-rejection",
                    "cause_service": "identity-provider",
                    "cause": "Consumers reject tokens signed by the rotated key.",
                    "prior": 0.38,
                    "next_step": "Sample verification failures by signing key ID.",
                    "status": "rejected",
                },
                {
                    "id": "hyp-gateway-failure",
                    "cause_service": "api-gateway",
                    "cause": "Gateway saturation delays authentication.",
                    "prior": 0.34,
                    "next_step": "Compare gateway saturation with verification latency.",
                    "status": "rejected",
                },
                {
                    "id": "hyp-network-jitter",
                    "cause_service": "api-gateway",
                    "cause": "Network jitter increases identity-provider round trips.",
                    "prior": 0.28,
                    "next_step": "Inspect inter-zone request duration.",
                },
            ],
        },
    },
]


def _service_tiers(graph: dict[str, Any]) -> dict[str, object]:
    return {node["id"]: node.get("tier", "tier-3") for node in graph["nodes"]}


def seed_database(session: Session) -> None:
    """Create the reproducible synthetic dataset without duplicating records."""

    existing_scenarios = set(session.scalars(select(Scenario.id)))
    existing_changes = set(session.scalars(select(ChangeRecord.id)))
    existing_incidents = set(session.scalars(select(IncidentRecord.id)))

    for order, raw_spec in enumerate(SCENARIO_SPECS, start=1):
        spec = deepcopy(raw_spec)
        scenario_id = spec["id"]
        change_spec = spec["change"]
        incident_spec = spec["incident"]
        graph = spec["graph"]

        if scenario_id not in existing_scenarios:
            session.add(
                Scenario(
                    id=scenario_id,
                    name=spec["name"],
                    description=spec["description"],
                    data_mode="synthetic",
                    is_active=order == 1,
                    sort_order=order,
                    active_change_id=change_spec["id"],
                    active_incident_id=incident_spec["id"],
                    service_graph=graph,
                )
            )
            existing_scenarios.add(scenario_id)
    session.flush()

    for raw_spec in SCENARIO_SPECS:
        spec = deepcopy(raw_spec)
        scenario_id = spec["id"]
        change_spec = spec["change"]
        incident_spec = spec["incident"]
        graph = spec["graph"]
        change_id = change_spec["id"]
        incident_id = incident_spec["id"]

        if change_id not in existing_changes:
            risk = calculate_change_risk(
                files_changed=change_spec["files_changed"],
                lines_added=change_spec["lines_added"],
                lines_deleted=change_spec["lines_deleted"],
                changed_services=change_spec["changed_services"],
                flags=change_spec["flags"],
                test_coverage=change_spec["test_coverage"],
                rollback_ready=change_spec["rollback_ready"],
                observability_score=change_spec["observability_score"],
                previous_failures=change_spec["previous_failures"],
                service_tiers=_service_tiers(graph),
                evidence_prefix=change_id,
            )
            blast_radius = calculate_blast_radius(
                nodes=graph["nodes"],
                edges=graph["edges"],
                changed_services=change_spec["changed_services"],
                evidence_prefix=change_id,
            )
            session.add(
                ChangeRecord(
                    id=change_id,
                    scenario_id=scenario_id,
                    data_mode="synthetic",
                    analysis_schema_version=ANALYSIS_SCHEMA_VERSION,
                    engine_version=ENGINE_VERSION,
                    scoring_policy_version=RISK_SCORING_POLICY_VERSION,
                    graph_version=GRAPH_VERSION,
                    title=change_spec["title"],
                    repository=change_spec["repository"],
                    author=change_spec["author"],
                    commit_sha=change_spec["commit_sha"],
                    branch=change_spec["branch"],
                    created_at=_timestamp(change_spec["created_at"]),
                    deployment_status=change_spec["deployment_status"],
                    deployment_environment=change_spec[
                        "deployment_environment"
                    ],
                    changed_services=change_spec["changed_services"],
                    files_changed=change_spec["files_changed"],
                    lines_added=change_spec["lines_added"],
                    lines_deleted=change_spec["lines_deleted"],
                    flags=change_spec["flags"],
                    test_coverage=change_spec["test_coverage"],
                    rollback_ready=change_spec["rollback_ready"],
                    observability_score=change_spec["observability_score"],
                    previous_failures=change_spec["previous_failures"],
                    risk=risk,
                    blast_radius=blast_radius,
                )
            )
            existing_changes.add(change_id)
    session.flush()

    for raw_spec in SCENARIO_SPECS:
        spec = deepcopy(raw_spec)
        scenario_id = spec["id"]
        change_id = spec["change"]["id"]
        incident_spec = spec["incident"]
        incident_id = incident_spec["id"]
        if incident_id not in existing_incidents:
            hypotheses = rank_hypotheses(
                evidence=incident_spec["evidence"],
                candidates=incident_spec["candidates"],
                limit=3,
            )
            selected_hypothesis_ids = {
                hypothesis["id"] for hypothesis in hypotheses
            }
            evidence = [
                {
                    **item,
                    "supports": [
                        hypothesis_id
                        for hypothesis_id in item.get("supports", [])
                        if hypothesis_id in selected_hypothesis_ids
                    ],
                    "contradicts": [
                        hypothesis_id
                        for hypothesis_id in item.get("contradicts", [])
                        if hypothesis_id in selected_hypothesis_ids
                    ],
                }
                for item in incident_spec["evidence"]
            ]
            session.add(
                IncidentRecord(
                    id=incident_id,
                    scenario_id=scenario_id,
                    data_mode="synthetic",
                    analysis_schema_version=ANALYSIS_SCHEMA_VERSION,
                    engine_version=ENGINE_VERSION,
                    scoring_policy_version=RCA_SCORING_POLICY_VERSION,
                    graph_version=GRAPH_VERSION_NOT_APPLICABLE,
                    title=incident_spec["title"],
                    severity=incident_spec["severity"],
                    status=incident_spec["status"],
                    started_at=_timestamp(incident_spec["started_at"]),
                    resolved_at=(
                        _timestamp(incident_spec["resolved_at"])
                        if incident_spec["resolved_at"]
                        else None
                    ),
                    affected_services=incident_spec["affected_services"],
                    correlated_change_id=change_id,
                    summary=incident_spec["summary"],
                    timeline=incident_spec["timeline"],
                    evidence=evidence,
                    hypotheses=hypotheses,
                )
            )
            existing_incidents.add(incident_id)

    if not session.scalar(
        select(func.count()).select_from(Scenario).where(Scenario.is_active.is_(True))
    ):
        first_scenario = session.scalar(
            select(Scenario).order_by(Scenario.sort_order, Scenario.id)
        )
        if first_scenario is not None:
            first_scenario.is_active = True
    session.commit()
