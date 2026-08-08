from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml


POLICY_SCHEMA_VERSION = "deployguard-policy/v0.1"
MAX_POLICY_BYTES = 256 * 1024

DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": POLICY_SCHEMA_VERSION,
    "requirements": {
        "tests": {"required": True, "skip_for_docs_only": True},
        "build": {"required": False},
        "coverage": {"required": False, "minimum_line_rate": 0.0},
        "security": {
            "required": False,
            "block_severities": ["critical", "high"],
        },
    },
    "path_rules": [
        {
            "id": "security-sensitive-change",
            "patterns": [
                ".github/workflows/**",
                "**/auth/**",
                "**/security/**",
                "**/migrations/**",
                "**/Dockerfile",
                "Dockerfile",
            ],
            "required_evidence": ["security"],
        }
    ],
}


@dataclass(frozen=True)
class LoadedPolicy:
    data: dict[str, Any]
    source: str
    sha256: str


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_policy(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("policy must be a YAML object")
    unknown_top_level = set(payload) - {"schema_version", "requirements", "path_rules"}
    if unknown_top_level:
        raise ValueError(f"unsupported policy fields: {sorted(unknown_top_level)}")
    if payload.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError(f"policy schema_version must be {POLICY_SCHEMA_VERSION}")
    requirements = payload.get("requirements")
    if not isinstance(requirements, dict):
        raise ValueError("policy requirements must be an object")

    supported = {"tests", "build", "coverage", "security"}
    unknown = set(requirements) - supported
    if unknown:
        raise ValueError(f"unsupported evidence requirements: {sorted(unknown)}")
    allowed_requirement_fields = {
        "tests": {"required", "skip_for_docs_only"},
        "build": {"required"},
        "coverage": {"required", "minimum_line_rate"},
        "security": {"required", "block_severities"},
    }
    for kind, config in requirements.items():
        if not isinstance(config, dict) or not isinstance(config.get("required", False), bool):
            raise ValueError(f"requirements.{kind} must contain a boolean required field")
        unknown_fields = set(config) - allowed_requirement_fields[kind]
        if unknown_fields:
            raise ValueError(
                f"unsupported requirements.{kind} fields: {sorted(unknown_fields)}"
            )
    skip_docs = requirements.get("tests", {}).get("skip_for_docs_only", False)
    if not isinstance(skip_docs, bool):
        raise ValueError("tests skip_for_docs_only must be boolean")

    coverage = requirements.get("coverage", {})
    threshold = coverage.get("minimum_line_rate", 0.0)
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValueError("coverage minimum_line_rate must be numeric")
    if not 0 <= float(threshold) <= 1:
        raise ValueError("coverage minimum_line_rate must be between 0 and 1")

    security = requirements.get("security", {})
    severities = security.get("block_severities", ["critical", "high"])
    if not isinstance(severities, list) or not all(
        severity in {"critical", "high", "medium", "low", "note"}
        for severity in severities
    ):
        raise ValueError("security block_severities contains an unsupported value")

    path_rules = payload.get("path_rules", [])
    if not isinstance(path_rules, list):
        raise ValueError("path_rules must be a list")
    seen_ids: set[str] = set()
    for rule in path_rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            raise ValueError("each path rule must have a string id")
        unknown_rule_fields = set(rule) - {"id", "patterns", "required_evidence"}
        if unknown_rule_fields:
            raise ValueError(
                f"unsupported path rule fields: {sorted(unknown_rule_fields)}"
            )
        if rule["id"] in seen_ids:
            raise ValueError(f"duplicate path rule id: {rule['id']}")
        seen_ids.add(rule["id"])
        patterns = rule.get("patterns")
        required_evidence = rule.get("required_evidence")
        if not isinstance(patterns, list) or not patterns or not all(
            isinstance(pattern, str) and pattern for pattern in patterns
        ):
            raise ValueError(f"path rule {rule['id']} must contain patterns")
        if not isinstance(required_evidence, list) or not all(
            item in supported for item in required_evidence
        ):
            raise ValueError(f"path rule {rule['id']} has invalid required_evidence")
    return payload


def parse_policy(raw: bytes, *, source: str) -> LoadedPolicy:
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("policy exceeds the 256 KiB safety limit")
    parsed = yaml.safe_load(raw.decode("utf-8"))
    policy = _validate_policy(parsed)
    return LoadedPolicy(
        data=policy,
        source=source,
        sha256=hashlib.sha256(canonical_json_bytes(policy)).hexdigest(),
    )


def builtin_policy() -> LoadedPolicy:
    raw = canonical_json_bytes(DEFAULT_POLICY)
    return LoadedPolicy(
        data=json.loads(raw),
        source="builtin:deployguard-policy/v0.1",
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_working_tree_policy(repository_root: Path, policy_path: str) -> LoadedPolicy:
    original = repository_root / policy_path
    if original.is_symlink():
        raise ValueError("policy path must not be a symbolic link")
    candidate = original.resolve(strict=True)
    if not candidate.is_relative_to(repository_root.resolve()):
        raise ValueError("policy path must remain inside the repository")
    return parse_policy(candidate.read_bytes(), source=f"working-tree:{policy_path}")


def matching_path_rules(policy: LoadedPolicy, paths: tuple[str, ...]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for rule in policy.data.get("path_rules", []):
        if any(
            fnmatchcase(path, pattern)
            for path in paths
            for pattern in rule["patterns"]
        ):
            matches.append(rule)
    return matches
