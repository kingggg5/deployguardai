from __future__ import annotations

import hashlib
import hmac

import pytest

from app.errors import DomainError
from app.verification_receipts import (
    _attestation_state,
    _receipt_hash,
    _verify_signature,
)


def test_receipt_hash_is_canonical_and_excludes_only_declared_hash() -> None:
    first = {"z": 1, "a": {"b": True}, "receipt_sha256": "placeholder"}
    second = {"a": {"b": True}, "z": 1, "receipt_sha256": "different"}
    assert _receipt_hash(first) == _receipt_hash(second)
    assert len(_receipt_hash(first)) == 64


def test_receipt_signature_requires_exact_hmac() -> None:
    secret = "s" * 32
    body = b'{"head_sha":"abc"}'
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    _verify_signature(body, f"sha256={signature}", secret)
    with pytest.raises(DomainError, match="invalid"):
        _verify_signature(body, "sha256=" + "0" * 64, secret)


def test_attestation_must_match_exact_head_and_receipt() -> None:
    assert (
        _attestation_state(
            {
                "subject_sha": "a" * 40,
                "receipt_sha256": "b" * 64,
                "verified_by": "github_artifact_attestation",
            },
            head_sha="a" * 40,
            receipt_sha256="b" * 64,
        )
        == "verified"
    )
    assert (
        _attestation_state(
            {
                "subject_sha": "c" * 40,
                "receipt_sha256": "b" * 64,
                "verified_by": "github_artifact_attestation",
            },
            head_sha="a" * 40,
            receipt_sha256="b" * 64,
        )
        == "invalid"
    )
