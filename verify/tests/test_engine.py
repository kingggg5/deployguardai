from __future__ import annotations

import copy

from deployguard_verify.engine import verify_change
from deployguard_verify.models import EvidenceItem, EvidenceState, GitChange
from deployguard_verify.policy import DEFAULT_POLICY, LoadedPolicy, canonical_json_bytes


def _change(*paths: str) -> GitChange:
    return GitChange(
        repository="example/repository",
        base_sha="a" * 40,
        head_sha="b" * 40,
        merge_base_sha="a" * 40,
        generated_at="2026-08-08T00:00:00+00:00",
        paths=tuple(paths or ("src/example.py",)),
        files_changed=len(paths or ("src/example.py",)),
        lines_added=10,
        lines_deleted=2,
        flags=(),
    )


def _policy(payload: dict[str, object] | None = None) -> LoadedPolicy:
    data = copy.deepcopy(payload or DEFAULT_POLICY)
    return LoadedPolicy(data=data, source="test", sha256="c" * 64)


def _evidence(
    kind: str,
    state: EvidenceState,
    *,
    metrics: dict[str, int | float | str | bool | None] | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        id=f"{kind}-fixture",
        kind=kind,
        state=state,
        source=f"artifacts/{kind}.json",
        source_sha="b" * 40,
        artifact_sha256="d" * 64,
        summary="fixture evidence",
        metrics=metrics or {},
    )


def test_verified_required_tests_produce_reproducible_pass_receipt() -> None:
    change = _change("src/example.py")
    evidence = [_evidence("tests", EvidenceState.PASS)]

    first = verify_change(change=change, policy=_policy(), evidence=evidence)
    second = verify_change(change=change, policy=_policy(), evidence=reversed(evidence))

    assert first.decision.value == "pass"
    assert first.receipt == second.receipt
    assert first.receipt["receipt_sha256"] == second.receipt["receipt_sha256"]
    assert canonical_json_bytes(first.receipt) == canonical_json_bytes(second.receipt)


def test_missing_required_evidence_is_review_not_fabricated_failure() -> None:
    result = verify_change(change=_change(), policy=_policy(), evidence=[])

    assert result.decision.value == "review"
    assert result.reason_codes == ("missing-tests-evidence",)
    assert result.receipt["evidence"] == []


def test_observed_test_failure_blocks_even_if_tests_are_optional() -> None:
    policy = copy.deepcopy(DEFAULT_POLICY)
    policy["requirements"]["tests"]["required"] = False

    result = verify_change(
        change=_change(),
        policy=_policy(policy),
        evidence=[_evidence("tests", EvidenceState.FAIL)],
    )

    assert result.decision.value == "block"
    assert "failed-tests-evidence" in result.reason_codes


def test_security_sensitive_path_requires_verified_sarif() -> None:
    result = verify_change(
        change=_change("backend/app/auth/oidc.py"),
        policy=_policy(),
        evidence=[_evidence("tests", EvidenceState.PASS)],
    )

    assert result.decision.value == "review"
    assert "path-rule-security-sensitive-change-security" in result.reason_codes
    assert result.receipt["policy"]["matched_path_rules"] == [
        "security-sensitive-change"
    ]


def test_high_security_finding_blocks() -> None:
    result = verify_change(
        change=_change("backend/app/auth/oidc.py"),
        policy=_policy(),
        evidence=[
            _evidence("tests", EvidenceState.PASS),
            _evidence(
                "security",
                EvidenceState.FAIL,
                metrics={"critical": 0, "high": 1, "medium": 0},
            ),
        ],
    )

    assert result.decision.value == "block"
    assert "security-finding-blocked" in result.reason_codes


def test_docs_only_change_can_skip_test_requirement() -> None:
    result = verify_change(
        change=_change("docs/QUICKSTART.md"),
        policy=_policy(),
        evidence=[],
    )

    assert result.decision.value == "pass"
