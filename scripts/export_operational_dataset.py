"""Build the public synthetic seed for DeployGuard Bench.

This exporter deliberately reads only the hand-authored synthetic scenario
specifications. Connected workspace data is not an accepted input: publishing
real operational evidence requires a separate consent, redaction, licensing,
and human-review pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.engines import (  # noqa: E402 - repository-local import
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    RCA_SCORING_POLICY_VERSION,
    rank_hypotheses,
)
from app.seed import SCENARIO_SPECS  # noqa: E402 - repository-local import


EXAMPLE_SCHEMA = "deployguard-operational-example/v1"
MANIFEST_SCHEMA = "deployguard-bench-manifest/v1"
DATASET_NAME = "DeployGuard Bench Synthetic Seed"
DATASET_VERSION = "0.1.0"
SCHEMA_PATH = (
    REPOSITORY_ROOT / "bench" / "schema" / "operational-example-v1.schema.json"
)
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / ".runtime" / "deployguard-bench"
PROHIBITED_PUBLIC_KEYS = {
    "access_token",
    "author",
    "email",
    "private_key",
    "provider_subject",
    "secret",
    "token",
}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _confirmed_candidate(
    candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    confirmed = [item for item in candidates if item.get("status") == "confirmed"]
    if len(confirmed) > 1:
        raise ValueError("a scenario cannot contain multiple confirmed ground truths")
    return confirmed[0] if confirmed else None


def _reference_integrity(
    evidence: Sequence[Mapping[str, Any]],
    hypotheses: Sequence[Mapping[str, Any]],
) -> float:
    evidence_ids = {str(item["id"]) for item in evidence}
    references = [
        str(reference)
        for hypothesis in hypotheses
        for reference in (
            list(hypothesis.get("evidence_ids", []))
            + list(hypothesis.get("counter_evidence_ids", []))
        )
    ]
    if not references:
        return 1.0
    return round(
        sum(reference in evidence_ids for reference in references) / len(references),
        3,
    )


def build_example(raw_spec: Mapping[str, Any]) -> dict[str, Any]:
    scenario_id = str(raw_spec["id"])
    change = dict(raw_spec["change"])
    incident = dict(raw_spec["incident"])
    graph = dict(raw_spec["graph"])
    candidates = [dict(item) for item in incident["candidates"]]
    evidence = [dict(item) for item in incident["evidence"]]
    hypotheses = rank_hypotheses(
        evidence=evidence,
        candidates=candidates,
        limit=len(candidates),
    )
    confirmed = _confirmed_candidate(candidates)
    ground_truth_id = str(confirmed["id"]) if confirmed else None
    verification_steps = [str(confirmed["next_step"])] if confirmed else []
    evaluation_reasons = [] if confirmed else ["missing_verified_ground_truth"]

    example: dict[str, Any] = {
        "schema": EXAMPLE_SCHEMA,
        "example_id": f"synthetic/{scenario_id}",
        "split": "development" if confirmed else "unverified",
        "data_mode": "synthetic",
        "tasks": [
            "root_cause_ranking",
            "evidence_grounded_explanation",
            "counter_evidence_reasoning",
            "verification_planning",
        ],
        "provenance": {
            "source_kind": "hand_authored_synthetic",
            "source_uri": f"backend/app/seed.py#SCENARIO_SPECS/{scenario_id}",
            "source_sha256": _sha256(_canonical_bytes(raw_spec)),
            "license": "Apache-2.0",
            "contains_customer_data": False,
            "contains_personal_data": False,
            "label_source": "scenario_author" if confirmed else None,
        },
        "deployment": {
            "change_id": str(change["id"]),
            "title": str(change["title"]),
            "repository": str(change["repository"]),
            "commit_sha": str(change["commit_sha"]),
            "branch": str(change["branch"]),
            "environment": str(change["deployment_environment"]),
            "status": str(change["deployment_status"]),
            "created_at": str(change["created_at"]),
            "changed_services": list(change["changed_services"]),
            "change_stats": {
                "files_changed": int(change["files_changed"]),
                "lines_added": int(change["lines_added"]),
                "lines_deleted": int(change["lines_deleted"]),
            },
            "flags": list(change["flags"]),
            "rollback_ready": bool(change["rollback_ready"]),
        },
        "topology": {
            "nodes": [dict(item) for item in graph["nodes"]],
            "edges": [dict(item) for item in graph["edges"]],
        },
        "incident": {
            "incident_id": str(incident["id"]),
            "correlated_change_id": str(change["id"]),
            "title": str(incident["title"]),
            "severity": str(incident["severity"]),
            "status": str(incident["status"]),
            "started_at": str(incident["started_at"]),
            "resolved_at": incident.get("resolved_at"),
            "affected_services": list(incident["affected_services"]),
            "summary": str(incident["summary"]),
            "timeline": [dict(item) for item in incident["timeline"]],
        },
        "evidence": evidence,
        "hypotheses": hypotheses,
        "ground_truth": {
            "status": "verified" if confirmed else "unverified",
            "hypothesis_id": ground_truth_id,
            "label_source": "scenario_author" if confirmed else None,
            "human_verdict": None,
        },
        "verification": {
            "status": "not_recorded",
            "steps": verification_steps,
            "observed_outcome": None,
        },
        "postmortem": {
            "status": (
                "summary_only" if incident.get("resolved_at") else "not_available"
            ),
            "summary": (
                str(incident["summary"]) if incident.get("resolved_at") else None
            ),
        },
        "quality": {
            "evidence_reference_integrity": _reference_integrity(
                evidence, hypotheses
            ),
            "evaluation_eligible": confirmed is not None,
            "evaluation_exclusion_reasons": evaluation_reasons,
            "training_eligible": False,
            "training_exclusion_reasons": [
                "development_split_reserved_for_evaluation",
                "no_human_verdict",
            ],
        },
        "engine": {
            "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "scoring_policy_version": RCA_SCORING_POLICY_VERSION,
        },
    }
    validate_example(example)
    return example


def _walk_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [
            nested
            for item in value.values()
            for nested in _walk_keys(item)
        ]
    if isinstance(value, list):
        return [nested for item in value for nested in _walk_keys(item)]
    return []


def validate_example(example: Mapping[str, Any]) -> None:
    if example.get("schema") != EXAMPLE_SCHEMA:
        raise ValueError(f"example schema must be {EXAMPLE_SCHEMA}")
    if example.get("data_mode") != "synthetic":
        raise ValueError("the public seed exporter accepts synthetic data only")
    prohibited = PROHIBITED_PUBLIC_KEYS.intersection(_walk_keys(example))
    if prohibited:
        raise ValueError(
            "public dataset contains prohibited identity or credential fields: "
            + ", ".join(sorted(prohibited))
        )

    evidence = example.get("evidence")
    hypotheses = example.get("hypotheses")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("example must contain evidence")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise ValueError("example must contain hypotheses")
    evidence_ids = [str(item["id"]) for item in evidence]
    hypothesis_ids = [str(item["id"]) for item in hypotheses]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("example contains duplicate evidence IDs")
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        raise ValueError("example contains duplicate hypothesis IDs")

    evidence_id_set = set(evidence_ids)
    for hypothesis in hypotheses:
        references = set(hypothesis.get("evidence_ids", [])) | set(
            hypothesis.get("counter_evidence_ids", [])
        )
        unknown = references - evidence_id_set
        if unknown:
            raise ValueError(
                "hypothesis references unknown evidence: "
                + ", ".join(sorted(str(item) for item in unknown))
            )

    ground_truth = example.get("ground_truth")
    if not isinstance(ground_truth, dict):
        raise ValueError("example must contain ground_truth")
    ground_truth_id = ground_truth.get("hypothesis_id")
    if ground_truth.get("status") == "verified" and ground_truth_id not in set(
        hypothesis_ids
    ):
        raise ValueError("verified ground truth must reference a known hypothesis")
    if ground_truth.get("human_verdict") is not None:
        raise ValueError("synthetic seed examples must not claim a human verdict")


def build_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"dataset schema not found: {SCHEMA_PATH}")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    examples = [build_example(spec) for spec in SCENARIO_SPECS]
    examples.sort(key=lambda item: str(item["example_id"]))
    jsonl = b"".join(_canonical_bytes(example) + b"\n" for example in examples)
    example_entries = [
        {
            "example_id": example["example_id"],
            "split": example["split"],
            "sha256": _sha256(_canonical_bytes(example)),
        }
        for example in examples
    ]
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "dataset": DATASET_NAME,
        "version": DATASET_VERSION,
        "data_mode": "synthetic",
        "license": "Apache-2.0",
        "example_schema": EXAMPLE_SCHEMA,
        "example_schema_sha256": _sha256(_canonical_bytes(schema)),
        "source_sha256": _sha256(_canonical_bytes(SCENARIO_SPECS)),
        "dataset_sha256": _sha256(jsonl),
        "total_examples": len(examples),
        "evaluation_eligible_examples": sum(
            bool(item["quality"]["evaluation_eligible"]) for item in examples
        ),
        "training_eligible_examples": sum(
            bool(item["quality"]["training_eligible"]) for item in examples
        ),
        "splits": {
            split: sum(item["split"] == split for item in examples)
            for split in sorted({str(item["split"]) for item in examples})
        },
        "examples": example_entries,
        "limitations": [
            "Hand-authored synthetic examples are not production incidents.",
            "Scenario-author labels are not human operator verdicts.",
            "The development split must not be reported as a hidden test set.",
            "No example in this seed release is approved for model training.",
        ],
    }
    return examples, manifest


def _render_bundle() -> dict[str, bytes]:
    examples, manifest = build_dataset()
    return {
        "examples.jsonl": b"".join(
            _canonical_bytes(example) + b"\n" for example in examples
        ),
        "manifest.json": (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }


def write_bundle(output_dir: Path, *, check: bool = False) -> dict[str, Any]:
    bundle = _render_bundle()
    if check:
        drift = [
            name
            for name, expected in bundle.items()
            if not (output_dir / name).is_file()
            or (output_dir / name).read_bytes() != expected
        ]
        if drift:
            raise ValueError("dataset artifact drift: " + ", ".join(sorted(drift)))
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in bundle.items():
            temporary = output_dir / f".{name}.tmp"
            temporary.write_bytes(content)
            temporary.replace(output_dir / name)
    _, manifest = build_dataset()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or verify the DeployGuard Bench synthetic seed bundle."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory containing examples.jsonl and manifest.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the existing bundle differs from the deterministic exporter.",
    )
    args = parser.parse_args()
    manifest = write_bundle(args.output_dir.resolve(), check=args.check)
    print(
        json.dumps(
            {
                "dataset": manifest["dataset"],
                "version": manifest["version"],
                "total_examples": manifest["total_examples"],
                "evaluation_eligible_examples": manifest[
                    "evaluation_eligible_examples"
                ],
                "training_eligible_examples": manifest[
                    "training_eligible_examples"
                ],
                "dataset_sha256": manifest["dataset_sha256"],
                "mode": "check" if args.check else "write",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
