"""Run the reproducible, evidence-only RCA benchmark evaluator.

The manifest contains immutable engine inputs and expected labels, never model
outputs. This runner invokes DeployGuard's allowlisted deterministic RCA engine
and derives every reported metric from the returned ranking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.engines import (  # noqa: E402 - backend path is repository-local
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    RCA_SCORING_POLICY_VERSION,
    rank_hypotheses,
)


DEFAULT_MANIFEST = Path(__file__).parent / "evaluation" / "manifest-v2.json"
MANIFEST_SCHEMA = "deployguard-evaluation-manifest/v2"
MAX_EPISODES = 500
MAX_CANDIDATES_PER_EPISODE = 50
MAX_EVIDENCE_PER_EPISODE = 500
MAX_MANIFEST_BYTES = 5_000_000
MAX_TEXT_LENGTH = 2_000
LEGACY_OUTPUT_FIELDS = {
    "prediction",
    "top_rank",
    "unsupported_claims",
    "citation_coverage",
}


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _text(value: object, field: str, *, maximum: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return value


def _ratio(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number between 0 and 1")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{field} must be a finite number between 0 and 1")
    return number


def _id_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    identifiers = [_text(item, field, maximum=128) for item in value]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{field} must not contain duplicate IDs")
    return identifiers


def _validate_episode(raw_episode: object, index: int) -> dict[str, Any]:
    episode = _mapping(raw_episode, f"episodes[{index}]")
    forbidden = LEGACY_OUTPUT_FIELDS.intersection(episode)
    if forbidden:
        raise ValueError(
            "evaluation manifests must not contain engine outputs: "
            + ", ".join(sorted(forbidden))
        )

    episode_id = _text(episode.get("id"), f"episodes[{index}].id", maximum=128)
    _text(episode.get("fault"), f"episode {episode_id}.fault", maximum=256)
    _text(episode.get("split"), f"episode {episode_id}.split", maximum=64)
    inputs = _mapping(episode.get("input"), f"episode {episode_id}.input")
    expected = _mapping(episode.get("expected"), f"episode {episode_id}.expected")

    candidates = inputs.get("candidates")
    evidence = inputs.get("evidence")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"episode {episode_id} must contain candidates")
    if len(candidates) > MAX_CANDIDATES_PER_EPISODE:
        raise ValueError(f"episode {episode_id} contains too many candidates")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"episode {episode_id} must contain evidence")
    if len(evidence) > MAX_EVIDENCE_PER_EPISODE:
        raise ValueError(f"episode {episode_id} contains too much evidence")

    candidate_ids: list[str] = []
    for candidate_index, raw_candidate in enumerate(candidates):
        candidate = _mapping(
            raw_candidate, f"episode {episode_id}.candidates[{candidate_index}]"
        )
        candidate_id = _text(
            candidate.get("id"),
            f"episode {episode_id}.candidates[{candidate_index}].id",
            maximum=128,
        )
        candidate_ids.append(candidate_id)
        _text(candidate.get("cause_service"), f"candidate {candidate_id}.cause_service")
        _text(candidate.get("cause"), f"candidate {candidate_id}.cause")
        _text(candidate.get("next_step"), f"candidate {candidate_id}.next_step")
        _ratio(candidate.get("prior", 0.5), f"candidate {candidate_id}.prior")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(f"episode {episode_id} contains duplicate candidate IDs")

    candidate_id_set = set(candidate_ids)
    evidence_ids: list[str] = []
    for evidence_index, raw_evidence in enumerate(evidence):
        item = _mapping(
            raw_evidence, f"episode {episode_id}.evidence[{evidence_index}]"
        )
        evidence_id = _text(
            item.get("id"),
            f"episode {episode_id}.evidence[{evidence_index}].id",
            maximum=128,
        )
        evidence_ids.append(evidence_id)
        _text(item.get("type"), f"evidence {evidence_id}.type", maximum=64)
        _ratio(item.get("quality", 0.5), f"evidence {evidence_id}.quality")
        supports = _id_list(item.get("supports", []), f"evidence {evidence_id}.supports")
        contradicts = _id_list(
            item.get("contradicts", []), f"evidence {evidence_id}.contradicts"
        )
        unknown = (set(supports) | set(contradicts)) - candidate_id_set
        if unknown:
            raise ValueError(
                f"evidence {evidence_id} references unknown candidates: "
                + ", ".join(sorted(unknown))
            )
        if set(supports).intersection(contradicts):
            raise ValueError(
                f"evidence {evidence_id} cannot support and contradict the same candidate"
            )
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError(f"episode {episode_id} contains duplicate evidence IDs")

    expected_id = _text(
        expected.get("root_cause_candidate_id"),
        f"episode {episode_id}.expected.root_cause_candidate_id",
        maximum=128,
    )
    if expected_id not in candidate_id_set:
        raise ValueError(
            f"episode {episode_id} expected root cause is not a candidate"
        )

    limit = inputs.get("limit", 3)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError(f"episode {episode_id}.input.limit must be between 1 and 10")
    return episode


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError(
            f"evaluation manifest must be no larger than {MAX_MANIFEST_BYTES} bytes"
        )
    raw = path.read_bytes()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("evaluation manifest must be an object")
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"evaluation manifest schema must be {MANIFEST_SCHEMA}")
    _text(payload.get("dataset"), "dataset", maximum=256)
    _text(payload.get("version"), "version", maximum=64)
    if payload.get("data_mode") not in {"synthetic", "public"}:
        raise ValueError("data_mode must be synthetic or public")
    _text(payload.get("license"), "license", maximum=128)
    provenance = _mapping(payload.get("provenance"), "provenance")
    _text(provenance.get("source"), "provenance.source")
    _text(provenance.get("created_at"), "provenance.created_at", maximum=64)
    episodes = payload.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("evaluation manifest must contain a non-empty episodes list")
    if len(episodes) > MAX_EPISODES:
        raise ValueError("evaluation manifest contains too many episodes")
    validated = [_validate_episode(episode, index) for index, episode in enumerate(episodes)]
    episode_ids = [str(episode["id"]) for episode in validated]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("evaluation manifest contains duplicate episode IDs")
    return payload, manifest_hash


def run_benchmark_eval(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest, manifest_sha256 = _load_manifest(manifest_path)
    episodes = manifest["episodes"]
    total = len(episodes)
    evaluated: list[dict[str, Any]] = []
    valid_reference_count = 0
    total_reference_count = 0
    hypotheses_with_references = 0
    total_hypotheses = 0

    for episode in episodes:
        inputs = episode["input"]
        candidates = inputs["candidates"]
        ranked = rank_hypotheses(
            evidence=inputs["evidence"],
            candidates=candidates,
            limit=len(candidates),
        )
        expected_id = episode["expected"]["root_cause_candidate_id"]
        expected_candidate = next(
            candidate for candidate in candidates if candidate["id"] == expected_id
        )
        expected_rank = next(
            item["rank"] for item in ranked if item["id"] == expected_id
        )
        top_limit = inputs.get("limit", 3)
        top_candidates = ranked[:top_limit]
        evidence_ids = {item["id"] for item in inputs["evidence"]}
        episode_reference_count = 0
        episode_valid_references = 0
        for hypothesis in ranked:
            references = hypothesis["evidence_ids"] + hypothesis["counter_evidence_ids"]
            total_hypotheses += 1
            if references:
                hypotheses_with_references += 1
            episode_reference_count += len(references)
            episode_valid_references += sum(
                1 for reference in references if reference in evidence_ids
            )
        total_reference_count += episode_reference_count
        valid_reference_count += episode_valid_references
        evaluated.append(
            {
                "id": episode["id"],
                "fault": episode["fault"],
                "split": episode["split"],
                "expected_candidate_id": expected_id,
                "expected_root_cause": expected_candidate["cause_service"],
                "expected_rank": expected_rank,
                "prediction_candidate_id": ranked[0]["id"],
                "prediction": ranked[0]["cause_service"],
                "top_candidates": [item["id"] for item in top_candidates],
                "evidence_reference_integrity": round(
                    episode_valid_references / episode_reference_count, 3
                )
                if episode_reference_count
                else 1.0,
            }
        )

    top1_correct = sum(1 for episode in evaluated if episode["expected_rank"] == 1)
    top3_correct = sum(1 for episode in evaluated if episode["expected_rank"] <= 3)
    mrr = sum(1.0 / episode["expected_rank"] for episode in evaluated) / total
    confusion = Counter(
        f"{episode['expected_root_cause']} -> {episode['prediction']}"
        for episode in evaluated
    )
    results: dict[str, Any] = {
        "evaluation_schema_version": "2.0.0",
        "benchmark_dataset": manifest.get("dataset", "DeployGuard benchmark"),
        "dataset_version": manifest.get("version", "unversioned"),
        "data_mode": manifest["data_mode"],
        "license": manifest["license"],
        "provenance": manifest["provenance"],
        "manifest_sha256": manifest_sha256,
        "engine_contract": "app.engines.rank_hypotheses",
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "scoring_policy_version": RCA_SCORING_POLICY_VERSION,
        "commit": os.environ.get("GITHUB_SHA", "unavailable"),
        "reference_environment": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "platform": platform.system().lower(),
        },
        "total_episodes": total,
        "top_1_accuracy": round(top1_correct / total, 3),
        "top_3_accuracy": round(top3_correct / total, 3),
        "mean_reciprocal_rank_mrr": round(mrr, 3),
        "unsupported_claims_rate": None,
        "unsupported_claims_status": "not_measured_requires_human_review",
        "citation_coverage": round(
            hypotheses_with_references / total_hypotheses, 3
        ),
        "evidence_reference_integrity": round(
            valid_reference_count / total_reference_count, 3
        )
        if total_reference_count
        else 1.0,
        "confusion": dict(sorted(confusion.items())),
        "failure_cases": [
            episode for episode in evaluated if episode["expected_rank"] != 1
        ],
        "episodes": evaluated,
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = run_benchmark_eval(args.manifest)
    encoded = json.dumps(results, indent=2, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
