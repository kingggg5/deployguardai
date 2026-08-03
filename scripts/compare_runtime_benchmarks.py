"""Compare the Python and .NET read-only engine on the same golden workload.

This is an engineering microbenchmark, not a production capacity claim. Both
runtimes execute the same nine immutable corpus cases in-process, without a
database, HTTP server, or network provider.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from statistics import median


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPOSITORY_ROOT / "scripts" / "evaluation" / "golden-corpus-v1.json"
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.engines import (  # noqa: E402
    calculate_blast_radius,
    calculate_change_risk,
    rank_hypotheses,
)


def _run_case(case: dict[str, Any]) -> object:
    engine = case["engine"]
    if engine == "calculate_change_risk":
        return calculate_change_risk(**case["input"])
    if engine == "calculate_blast_radius":
        return calculate_blast_radius(**case["input"])
    if engine == "rank_hypotheses":
        return rank_hypotheses(**case["input"])
    raise ValueError(f"unsupported engine: {engine}")


def _percentile(values: list[float], fraction: float) -> float:
    index = min(len(values) - 1, max(0, int(fraction * len(values) + 0.999999) - 1))
    return values[index]


def _python_benchmark(cases: list[dict[str, Any]], iterations: int) -> dict[str, Any]:
    for _ in range(25):
        for case in cases:
            _run_case(case)
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        for case in cases:
            _run_case(case)
        samples.append((time.perf_counter_ns() - started) / 1_000.0)
    samples.sort()
    operations = iterations * len(cases)
    elapsed_seconds = sum(samples) / 1_000_000.0
    return {
        "runtime": "python-3.12",
        "iterations": iterations,
        "operations": operations,
        "p50_microseconds": _percentile(samples, 0.50),
        "p95_microseconds": _percentile(samples, 0.95),
        "p99_microseconds": _percentile(samples, 0.99),
        "operations_per_second": operations / elapsed_seconds,
        "workload": "all v1 golden cases per batch; in-process deterministic engines; no database or network",
    }


def _dotnet_report(project: Path, iterations: int) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "dotnet",
            "run",
            "--project",
            str(project),
            "--configuration",
            "Release",
            "--no-build",
            "--",
            "--verify",
            "--iterations",
            str(iterations),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("{"):
            report = json.loads(line)
            return {"runtime": "dotnet-10", **report["performance"]}
    raise RuntimeError(".NET spike did not emit a JSON report")


def _median_report(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        raise ValueError("at least one benchmark run is required")
    numeric_fields = {
        "p50_microseconds",
        "p95_microseconds",
        "p99_microseconds",
        "operations_per_second",
    }
    result = dict(runs[0])
    for field in numeric_fields:
        result[field] = median(float(run[field]) for run in runs)
    result["sample_count"] = len(runs)
    result["sample_p95_microseconds"] = [run["p95_microseconds"] for run in runs]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / ".runtime" / "runtime-benchmark-comparison.json",
    )
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
        help="number of independent samples to median; use 1 for a single run",
    )
    parser.add_argument(
        "--dotnet-project",
        type=Path,
        default=REPOSITORY_ROOT / "spikes" / "dotnet-readonly" / "DeployGuard.ReadOnlySpike.csproj",
    )
    args = parser.parse_args()
    cases = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["cases"]
    if args.iterations <= 0 or args.repetitions <= 0:
        parser.error("--iterations and --repetitions must be positive")
    python_runs = [_python_benchmark(cases, args.iterations) for _ in range(args.repetitions)]
    dotnet_runs = [
        _dotnet_report(args.dotnet_project, args.iterations)
        for _ in range(args.repetitions)
    ]
    python_result = _median_report(python_runs)
    dotnet_result = _median_report(dotnet_runs)
    report = {
        "schema": "deployguard-runtime-comparison/v1",
        "data_mode": "synthetic",
        "corpus": "scripts/evaluation/golden-corpus-v1.json",
        "cases": len(cases),
        "repetitions": args.repetitions,
        "python": python_result,
        "dotnet": dotnet_result,
        "dotnet_p95_latency_ratio": dotnet_result["p95_microseconds"]
        / python_result["p95_microseconds"],
        "dotnet_engine_faster_on_p95": dotnet_result["p95_microseconds"]
        < python_result["p95_microseconds"],
        "limitations": [
            "engine-only microbenchmark; no HTTP, PostgreSQL, worker, or provider IO",
            "not a capacity or production SLO claim",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
