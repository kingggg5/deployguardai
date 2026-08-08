from __future__ import annotations

import copy
import json

import pytest

from deployguard_verify.policy import DEFAULT_POLICY, parse_policy


def _raw(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_policy_rejects_unknown_top_level_field() -> None:
    payload = copy.deepcopy(DEFAULT_POLICY)
    payload["allow_missing_evidence"] = True

    with pytest.raises(ValueError, match="unsupported policy fields"):
        parse_policy(_raw(payload), source="test")


def test_policy_rejects_misspelled_requirement() -> None:
    payload = copy.deepcopy(DEFAULT_POLICY)
    payload["requirements"]["tests"]["requried"] = False

    with pytest.raises(ValueError, match="unsupported requirements.tests fields"):
        parse_policy(_raw(payload), source="test")


def test_default_policy_is_valid_and_canonical() -> None:
    first = parse_policy(_raw(DEFAULT_POLICY), source="first")
    second = parse_policy(_raw(copy.deepcopy(DEFAULT_POLICY)), source="second")

    assert first.data == second.data
    assert first.sha256 == second.sha256
