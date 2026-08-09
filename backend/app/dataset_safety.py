"""Deterministic redaction and leakage checks for governed dataset bundles.

This module is deliberately conservative: it reports findings with JSON
paths, never silently drops records, and keeps the connected exporter closed
until a human reviews the resulting artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable


_SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I)),
)
_PII_PATTERNS = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone", re.compile(r"\b(?:\+?\d[\d ()-]{8,}\d)\b")),
)
_SENSITIVE_KEYS = re.compile(
    r"(?:^|_)(?:password|secret|token|api_key|private_key|authorization|"
    r"customer_id|account_id|user_email|email|phone|address)(?:$|_)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class RedactionFinding:
    path: str
    category: str
    action: str


def _category(value: str) -> str | None:
    for category, pattern in (*_SECRET_PATTERNS, *_PII_PATTERNS):
        if pattern.search(value):
            return category
    return None


def redact_payload(
    value: Any,
    *,
    path: str = "$",
) -> tuple[Any, tuple[RedactionFinding, ...]]:
    """Return a sanitized copy plus every finding that caused a rewrite."""

    findings: list[RedactionFinding] = []
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for raw_key, nested in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if _SENSITIVE_KEYS.search(key):
                output[key] = "[REDACTED:sensitive-field]"
                findings.append(RedactionFinding(child_path, "sensitive-field", "redacted"))
                continue
            sanitized, nested_findings = redact_payload(nested, path=child_path)
            output[key] = sanitized
            findings.extend(nested_findings)
        return output, tuple(findings)
    if isinstance(value, list):
        output: list[Any] = []
        for index, nested in enumerate(value):
            sanitized, nested_findings = redact_payload(
                nested, path=f"{path}[{index}]"
            )
            output.append(sanitized)
            findings.extend(nested_findings)
        return output, tuple(findings)
    if isinstance(value, str):
        sanitized = value
        matched: set[str] = set()
        for category, pattern in (*_SECRET_PATTERNS, *_PII_PATTERNS):
            if pattern.search(sanitized):
                sanitized = pattern.sub(f"[REDACTED:{category}]", sanitized)
                matched.add(category)
        findings.extend(
            RedactionFinding(path, category, "redacted") for category in sorted(matched)
        )
        return sanitized, tuple(findings)
    return value, ()


def leakage_findings(records: Iterable[dict[str, Any]]) -> tuple[dict[str, str], ...]:
    """Find exact duplicate content crossing frozen dataset splits."""

    by_digest: dict[str, tuple[str, str]] = {}
    findings: list[dict[str, str]] = []
    for record in records:
        record_id = str(record.get("example_id") or record.get("id") or "unknown")
        split = str(record.get("split") or "unknown")
        material = record.get("content", record)
        # A stable JSON representation makes the leakage decision portable
        # across Python versions and independent of dictionary insertion order.
        try:
            canonical = json.dumps(
                material,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            canonical = repr(material).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        previous = by_digest.get(digest)
        if previous is not None and previous[1] != split:
            findings.append(
                {
                    "kind": "duplicate-across-splits",
                    "digest": digest,
                    "first_example": previous[0],
                    "second_example": record_id,
                    "first_split": previous[1],
                    "second_split": split,
                }
            )
        else:
            by_digest[digest] = (record_id, split)
    return tuple(findings)
