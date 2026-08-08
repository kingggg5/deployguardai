from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Iterable

from .models import Decision, EvidenceItem, EvidenceState, GitChange, VerificationResult
from .policy import LoadedPolicy, canonical_json_bytes, matching_path_rules


RECEIPT_SCHEMA_VERSION = "deployguard-evidence-receipt/v0.1"
VERIFY_ENGINE_VERSION = "deployguard-verify/0.1.0"


def _add_reason(
    reason_codes: list[str],
    reasons: list[str],
    code: str,
    message: str,
) -> None:
    if code not in reason_codes:
        reason_codes.append(code)
        reasons.append(message)


def _required(
    policy: LoadedPolicy,
    kind: str,
    *,
    docs_only: bool,
) -> bool:
    config = policy.data.get("requirements", {}).get(kind, {})
    if kind == "tests" and docs_only and config.get("skip_for_docs_only", False):
        return False
    return bool(config.get("required", False))


def _security_blocks(item: EvidenceItem, blocked_severities: set[str]) -> bool:
    return any(int(item.metrics.get(severity, 0) or 0) > 0 for severity in blocked_severities)


def _evaluate_decision(
    change: GitChange,
    policy: LoadedPolicy,
    evidence: tuple[EvidenceItem, ...],
) -> tuple[Decision, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    by_kind: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in evidence:
        by_kind[item.kind].append(item)

    blocks: list[tuple[str, str]] = []
    reviews: list[tuple[str, str]] = []
    matched_rules: list[str] = []

    if not change.paths:
        reviews.append(("no-change", "The selected base and head contain no changed paths."))

    requirements = policy.data.get("requirements", {})
    for kind in ("tests", "build", "coverage", "security"):
        items = by_kind.get(kind, [])
        is_required = _required(policy, kind, docs_only=change.docs_only)
        if is_required and not items:
            reviews.append(
                (
                    f"missing-{kind}-evidence",
                    f"Required {kind} evidence was not provided.",
                )
            )
            continue
        if is_required and items and not any(item.state == EvidenceState.PASS for item in items):
            if any(item.state == EvidenceState.FAIL for item in items):
                blocks.append(
                    (
                        f"failed-{kind}-evidence",
                        f"Required {kind} evidence contains a failure.",
                    )
                )
            else:
                reviews.append(
                    (
                        f"unknown-{kind}-evidence",
                        f"Required {kind} evidence could not be verified for the head SHA.",
                    )
                )

    for kind in ("tests", "build"):
        if any(item.state == EvidenceState.FAIL for item in by_kind.get(kind, [])):
            blocks.append(
                (
                    f"failed-{kind}-evidence",
                    f"Observed {kind} evidence contains a failure.",
                )
            )

    coverage_threshold = float(
        requirements.get("coverage", {}).get("minimum_line_rate", 0.0)
    )
    if coverage_threshold > 0:
        rates = [
            float(item.metrics["line_rate"])
            for item in by_kind.get("coverage", [])
            if item.state != EvidenceState.UNKNOWN and "line_rate" in item.metrics
        ]
        if rates and min(rates) < coverage_threshold:
            blocks.append(
                (
                    "coverage-below-policy",
                    f"Observed line coverage is below the {coverage_threshold:.1%} policy threshold.",
                )
            )

    blocked_severities = set(
        requirements.get("security", {}).get(
            "block_severities", ["critical", "high"]
        )
    )
    if any(
        item.state != EvidenceState.UNKNOWN
        and _security_blocks(item, blocked_severities)
        for item in by_kind.get("security", [])
    ):
        blocks.append(
            (
                "security-finding-blocked",
                "SARIF contains a finding at a policy-blocking severity.",
            )
        )

    for rule in matching_path_rules(policy, change.paths):
        matched_rules.append(rule["id"])
        for kind in rule["required_evidence"]:
            items = by_kind.get(kind, [])
            if not any(item.state == EvidenceState.PASS for item in items):
                reviews.append(
                    (
                        f"path-rule-{rule['id']}-{kind}",
                        f"Path rule {rule['id']} requires verified {kind} evidence.",
                    )
                )

    reason_codes: list[str] = []
    reasons: list[str] = []
    if blocks:
        decision = Decision.BLOCK
        for code, reason in sorted(blocks):
            _add_reason(reason_codes, reasons, code, reason)
    elif reviews:
        decision = Decision.REVIEW
        for code, reason in sorted(reviews):
            _add_reason(reason_codes, reasons, code, reason)
    else:
        decision = Decision.PASS
        _add_reason(
            reason_codes,
            reasons,
            "policy-satisfied",
            "All required evidence is present, SHA-matched, and policy-compliant.",
        )
    return decision, tuple(reason_codes), tuple(reasons), tuple(sorted(matched_rules))


def verify_change(
    *,
    change: GitChange,
    policy: LoadedPolicy,
    evidence: Iterable[EvidenceItem],
) -> VerificationResult:
    evidence_items = tuple(
        sorted(evidence, key=lambda item: (item.kind, item.source, item.id))
    )
    decision, reason_codes, reasons, matched_rules = _evaluate_decision(
        change, policy, evidence_items
    )
    body: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "engine_version": VERIFY_ENGINE_VERSION,
        "generated_at": change.generated_at,
        "repository": {
            "name": change.repository,
            "base_sha": change.base_sha,
            "head_sha": change.head_sha,
            "merge_base_sha": change.merge_base_sha,
        },
        "policy": {
            "schema_version": policy.data["schema_version"],
            "source": policy.source,
            "sha256": policy.sha256,
            "matched_path_rules": list(matched_rules),
        },
        "change": {
            "files_changed": change.files_changed,
            "lines_added": change.lines_added,
            "lines_deleted": change.lines_deleted,
            "paths": list(change.paths),
            "flags": list(change.flags),
            "docs_only": change.docs_only,
        },
        "evidence": [item.to_dict() for item in evidence_items],
        "decision": {
            "status": decision.value,
            "reason_codes": list(reason_codes),
            "reasons": list(reasons),
        },
    }
    receipt_sha256 = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    receipt = {**body, "receipt_sha256": receipt_sha256}
    return VerificationResult(
        decision=decision,
        reason_codes=reason_codes,
        reasons=reasons,
        receipt=receipt,
    )
