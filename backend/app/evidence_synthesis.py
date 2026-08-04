"""Evidence-only incident explanation contract.

This module deliberately has no provider SDK, network client, or prompt.  It
creates a small deterministic explanation from already ranked hypotheses and
rejects output that cites anything outside the incident evidence bundle.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable

from .schemas import (
    EvidenceCitedStatement,
    EvidenceSynthesisHypothesis,
    EvidenceSynthesisResponse,
    Hypothesis,
    IncidentDetail,
)


EVIDENCE_SYNTHESIS_CONTRACT_VERSION = "evidence-synthesis-v1"
CITATION_VALIDATOR_VERSION = "citation-validator-v1"
DETERMINISTIC_TEMPLATE_MODEL = "deterministic-evidence-template-v1"


class CitationValidationError(ValueError):
    """Raised when an explanation refers to evidence outside its bundle."""


def _statement_evidence_ids(
    synthesis: EvidenceSynthesisResponse,
) -> Iterable[tuple[str, list[str]]]:
    for index, statement in enumerate(synthesis.summary):
        yield f"summary[{index}]", statement.evidence_ids
    for index, hypothesis in enumerate(synthesis.explained_hypotheses):
        yield (
            f"explained_hypotheses[{index}]",
            hypothesis.explanation.evidence_ids,
        )
    for index, statement in enumerate(synthesis.uncertainty):
        yield f"uncertainty[{index}]", statement.evidence_ids


def evidence_bundle_sha256(incident: IncidentDetail) -> str:
    """Hash the exact, normalized evidence and hypothesis inputs used.

    The digest can be retained in audit data without copying raw evidence into
    a secondary event log.  It is not a replacement for the source ledger.
    """

    bundle = {
        "incident_id": incident.id,
        "evidence": [
            item.model_dump(mode="json")
            for item in sorted(incident.evidence, key=lambda item: item.id)
        ],
        "hypotheses": [
            item.model_dump(mode="json")
            for item in sorted(
                incident.hypotheses, key=lambda item: (item.rank, item.id)
            )
        ],
    }
    canonical = json.dumps(
        bundle,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_evidence_synthesis(
    incident: IncidentDetail,
    synthesis: EvidenceSynthesisResponse,
) -> None:
    """Verify that every emitted statement cites valid, relevant evidence."""

    if synthesis.incident_id != incident.id:
        raise CitationValidationError("Synthesis incident does not match bundle")
    if synthesis.contract_version != EVIDENCE_SYNTHESIS_CONTRACT_VERSION:
        raise CitationValidationError("Unsupported evidence synthesis contract")
    if synthesis.validator_version != CITATION_VALIDATOR_VERSION:
        raise CitationValidationError("Unsupported citation validator")
    if synthesis.evidence_bundle_sha256 != evidence_bundle_sha256(incident):
        raise CitationValidationError("Evidence bundle digest does not match")
    if synthesis.unsupported_claims_count != 0:
        raise CitationValidationError("Evidence-only synthesis has unsupported claims")

    known_evidence_ids = {item.id for item in incident.evidence}
    if not known_evidence_ids:
        raise CitationValidationError("Incident has no evidence to cite")
    for location, evidence_ids in _statement_evidence_ids(synthesis):
        unknown_ids = sorted(set(evidence_ids) - known_evidence_ids)
        if unknown_ids:
            raise CitationValidationError(
                f"{location} cites unknown evidence IDs: {', '.join(unknown_ids)}"
            )

    hypotheses_by_id = {item.id: item for item in incident.hypotheses}
    for item in synthesis.explained_hypotheses:
        source_hypothesis = hypotheses_by_id.get(item.hypothesis_id)
        if source_hypothesis is None:
            raise CitationValidationError(
                f"Explanation cites unknown hypothesis ID: {item.hypothesis_id}"
            )
        if item.rank != source_hypothesis.rank:
            raise CitationValidationError(
                f"Explanation rank does not match hypothesis: {item.hypothesis_id}"
            )
        allowed_evidence_ids = set(source_hypothesis.evidence_ids)
        allowed_evidence_ids.update(source_hypothesis.counter_evidence_ids)
        if not set(item.explanation.evidence_ids) <= allowed_evidence_ids:
            raise CitationValidationError(
                f"Explanation cites evidence unrelated to hypothesis: {item.hypothesis_id}"
            )

    statements = list(_statement_evidence_ids(synthesis))
    citation_coverage = (
        sum(bool(evidence_ids) for _, evidence_ids in statements) / len(statements)
        if statements
        else 0.0
    )
    if not math.isclose(
        synthesis.citation_coverage,
        citation_coverage,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise CitationValidationError("Citation coverage does not match statements")


def _hypothesis_citations(hypothesis: Hypothesis) -> list[str]:
    return list(
        dict.fromkeys(
            [*hypothesis.evidence_ids, *hypothesis.counter_evidence_ids]
        )
    )


def build_evidence_synthesis(incident: IncidentDetail) -> EvidenceSynthesisResponse:
    """Build a bounded explanation from ranked hypotheses and source evidence."""

    known_evidence_ids = {item.id for item in incident.evidence}
    candidates = [
        hypothesis
        for hypothesis in sorted(
            incident.hypotheses, key=lambda item: (item.rank, item.id)
        )
        if _hypothesis_citations(hypothesis)
        and set(_hypothesis_citations(hypothesis)) <= known_evidence_ids
    ]
    if not known_evidence_ids or not candidates:
        raise CitationValidationError(
            "Incident requires at least one ranked hypothesis with valid evidence"
        )

    selected = candidates[:3]
    primary = selected[0]
    primary_citations = _hypothesis_citations(primary)
    cited_evidence = [
        item for item in incident.evidence if item.id in primary_citations
    ]
    lowest_quality = min(cited_evidence, key=lambda item: (item.quality, item.id))

    response = EvidenceSynthesisResponse(
        incident_id=incident.id,
        synthesis_mode="deterministic_evidence_template",
        model_used=DETERMINISTIC_TEMPLATE_MODEL,
        contract_version=EVIDENCE_SYNTHESIS_CONTRACT_VERSION,
        validator_version=CITATION_VALIDATOR_VERSION,
        evidence_bundle_sha256=evidence_bundle_sha256(incident),
        confidence=round(
            sum(item.confidence for item in selected) / len(selected), 2
        ),
        summary=[
            EvidenceCitedStatement(
                text=(
                    f"Rank {primary.rank} hypothesis: "
                    f"{primary.cause_service} — {primary.cause}."
                ),
                evidence_ids=primary_citations,
            )
        ],
        hypotheses=selected,
        explained_hypotheses=[
            EvidenceSynthesisHypothesis(
                hypothesis_id=item.id,
                rank=item.rank,
                explanation=EvidenceCitedStatement(
                    text=item.reasoning,
                    evidence_ids=_hypothesis_citations(item),
                ),
            )
            for item in selected
        ],
        uncertainty=[
            EvidenceCitedStatement(
                text=(
                    f"Verify {lowest_quality.id} from {lowest_quality.source}; "
                    f"its recorded evidence quality is {lowest_quality.quality:.2f}."
                ),
                evidence_ids=[lowest_quality.id],
            )
        ],
        unsupported_claims_count=0,
        citation_coverage=1.0,
    )
    validate_evidence_synthesis(incident, response)
    return response
