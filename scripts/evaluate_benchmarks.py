"""Run the reproducible, evidence-only benchmark evaluator.

The evaluator intentionally reads a versioned manifest instead of embedding
episodes in code. It does not call an LLM and produces a machine-readable
result that CI can archive for review when scoring changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path(__file__).parent / "evaluation" / "manifest-v1.json"


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw)
    episodes = payload.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("evaluation manifest must contain a non-empty episodes list")
    required = {"id", "fault", "true_root_cause", "prediction", "top_rank"}
    for episode in episodes:
        if not required.issubset(episode):
            missing = sorted(required.difference(episode))
            raise ValueError(f"episode is missing required fields: {missing}")
        if int(episode["top_rank"]) < 1:
            raise ValueError("top_rank must be at least 1")
    return payload, manifest_hash


def run_benchmark_eval(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    started = time.perf_counter()
    manifest, manifest_sha256 = _load_manifest(manifest_path)
    episodes = manifest["episodes"]
    total = len(episodes)
    top1_correct = sum(1 for episode in episodes if int(episode["top_rank"]) == 1)
    top3_correct = sum(1 for episode in episodes if int(episode["top_rank"]) <= 3)
    mrr = sum(1.0 / int(episode["top_rank"]) for episode in episodes) / total
    confusion = Counter(
        f"{episode['true_root_cause']} -> {episode['prediction']}"
        for episode in episodes
    )
    results: dict[str, Any] = {
        "benchmark_dataset": manifest.get("dataset", "DeployGuard benchmark"),
        "dataset_version": manifest.get("version", "unversioned"),
        "manifest_sha256": manifest_sha256,
        "total_episodes": total,
        "top_1_accuracy": round(top1_correct / total, 3),
        "top_3_accuracy": round(top3_correct / total, 3),
        "mean_reciprocal_rank_mrr": round(mrr, 3),
        "unsupported_claims_rate": round(
            sum(float(episode.get("unsupported_claims", 0)) for episode in episodes)
            / total,
            3,
        ),
        "citation_coverage": round(
            sum(float(episode.get("citation_coverage", 0)) for episode in episodes)
            / total,
            3,
        ),
        "confusion": dict(sorted(confusion.items())),
        "eval_duration_seconds": round(time.perf_counter() - started, 3),
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
