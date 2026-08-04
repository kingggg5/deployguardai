import pytest

from app.evidence_synthesis import (
    CitationValidationError,
    build_evidence_synthesis,
    validate_evidence_synthesis,
)
from app.schemas import IncidentDetail


def _incident() -> IncidentDetail:
    return IncidentDetail.model_validate(
        {
            "id": "inc-1",
            "scenario_id": "scenario-1",
            "data_mode": "connected",
            "analysis_schema_version": "analysis-v1",
            "engine_version": "engine-v1",
            "scoring_policy_version": "policy-v1",
            "graph_version": "graph-v1",
            "title": "Checkout latency elevated",
            "severity": "SEV-2",
            "status": "investigating",
            "started_at": "2026-08-01T00:00:00Z",
            "resolved_at": None,
            "affected_services": ["checkout-api"],
            "correlated_change_id": None,
            "summary": "A cited evidence bundle is available.",
            "timeline": [],
            "evidence": [
                {
                    "id": "ev-trace",
                    "type": "trace",
                    "source": "otel",
                    "timestamp": "2026-08-01T00:01:00Z",
                    "summary": "Timeout before retry fan-out.",
                    "value": "timeout",
                    "quality": 0.9,
                    "service_id": "checkout-api",
                    "supports": ["hyp-timeout"],
                    "contradicts": [],
                }
            ],
            "hypotheses": [
                {
                    "id": "hyp-timeout",
                    "rank": 1,
                    "cause_service": "checkout-api",
                    "cause": "Retry timeout is too short",
                    "confidence": 0.8,
                    "score": 80,
                    "evidence_ids": ["ev-trace"],
                    "counter_evidence_ids": [],
                    "reasoning": "The trace records a timeout before retries.",
                    "next_step": "Inspect the timeout configuration.",
                    "status": "open",
                }
            ],
            "feedback": [],
        }
    )


def test_evidence_synthesis_is_deterministic_and_citation_gated() -> None:
    incident = _incident()

    first = build_evidence_synthesis(incident)
    second = build_evidence_synthesis(incident)

    assert first == second
    assert first.unsupported_claims_count == 0
    assert first.citation_coverage == 1.0
    assert first.summary[0].evidence_ids == ["ev-trace"]
    validate_evidence_synthesis(incident, first)


def test_citation_validator_rejects_unknown_evidence_id() -> None:
    incident = _incident()
    synthesis = build_evidence_synthesis(incident)
    synthesis.summary[0].evidence_ids = ["ev-not-in-bundle"]

    with pytest.raises(CitationValidationError, match="unknown evidence IDs"):
        validate_evidence_synthesis(incident, synthesis)
