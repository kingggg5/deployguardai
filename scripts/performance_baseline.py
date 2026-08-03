"""Run a reproducible local performance baseline without claiming production SLOs."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import tracemalloc
from typing import Any, Callable
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import Settings  # noqa: E402
from app.database import Database  # noqa: E402
from app.engines import (  # noqa: E402
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    RISK_SCORING_POLICY_VERSION,
    calculate_blast_radius,
    calculate_change_risk,
)
from app.job_models import BackgroundJob  # noqa: E402
from app.job_queue import requeue_expired_jobs  # noqa: E402
from app.main import create_app  # noqa: E402


RESULT_SCHEMA_VERSION = "deployguard-performance-result/v1"
PROFILES = {
    "test": {
        "risk_iterations": 5,
        "graph_sizes": [10],
        "graph_repetitions": 1,
        "startup_samples": 1,
        "recovery_jobs": 5,
    },
    "quick": {
        "risk_iterations": 250,
        "graph_sizes": [10, 100, 500],
        "graph_repetitions": 5,
        "startup_samples": 2,
        "recovery_jobs": 100,
    },
    "standard": {
        "risk_iterations": 2_000,
        "graph_sizes": [100, 1_000, 5_000],
        "graph_repetitions": 15,
        "startup_samples": 5,
        "recovery_jobs": 1_000,
    },
}


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("at least one sample is required")
    index = max(0, math.ceil(percentile * len(sorted_values)) - 1)
    return sorted_values[index]


def _latency_summary(samples_ns: list[int]) -> dict[str, float | int]:
    values = sorted(sample / 1_000_000 for sample in samples_ns)
    return {
        "samples": len(values),
        "min_ms": round(values[0], 3),
        "p50_ms": round(_percentile(values, 0.50), 3),
        "p95_ms": round(_percentile(values, 0.95), 3),
        "p99_ms": round(_percentile(values, 0.99), 3),
        "max_ms": round(values[-1], 3),
    }


def _measure_calls(call: Callable[[], object], iterations: int) -> tuple[list[int], object]:
    samples: list[int] = []
    last_result: object = None
    for _ in range(iterations):
        started = perf_counter_ns()
        last_result = call()
        samples.append(perf_counter_ns() - started)
    return samples, last_result


def _throughput(iterations: int, samples_ns: list[int]) -> float:
    elapsed_seconds = sum(samples_ns) / 1_000_000_000
    return round(iterations / elapsed_seconds, 2) if elapsed_seconds else 0.0


def _result_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _risk_measurement(iterations: int) -> dict[str, object]:
    inputs = {
        "files_changed": 18,
        "lines_added": 640,
        "lines_deleted": 170,
        "changed_services": ["checkout-api", "payment-adapter", "order-service"],
        "flags": ["retry-policy", "api-contract"],
        "test_coverage": 0.78,
        "rollback_ready": True,
        "observability_score": 0.86,
        "previous_failures": 2,
        "service_tiers": {
            "checkout-api": "tier-1",
            "payment-adapter": "tier-1",
            "order-service": "tier-2",
        },
        "evidence_prefix": "performance-baseline",
    }
    samples, result = _measure_calls(
        lambda: calculate_change_risk(**inputs),
        iterations,
    )
    return {
        "contract": "app.engines.calculate_change_risk",
        "iterations": iterations,
        "latency": _latency_summary(samples),
        "throughput_ops_per_second": _throughput(iterations, samples),
        "output_sha256": _result_digest(result),
    }


def _graph_input(node_count: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    nodes = [
        {
            "id": f"service-{index}",
            "label": f"Service {index}",
            "kind": "service",
            "team": f"team-{index % 8}",
            "tier": f"tier-{(index % 3) + 1}",
            "health": "healthy",
        }
        for index in range(node_count)
    ]
    edges: list[dict[str, object]] = []
    for index in range(node_count - 1):
        edges.append(
            {
                "source": f"service-{index}",
                "target": f"service-{index + 1}",
                "relation": "runtime-dependency",
                "confidence": 0.98,
                "active": True,
            }
        )
        if index + 2 < node_count:
            edges.append(
                {
                    "source": f"service-{index}",
                    "target": f"service-{index + 2}",
                    "relation": "async-dependency",
                    "confidence": 0.85,
                    "active": True,
                }
            )
    if node_count > 2:
        edges.append(
            {
                "source": f"service-{node_count - 1}",
                "target": "service-0",
                "relation": "cycle-boundary",
                "confidence": 0.75,
                "active": True,
            }
        )
    return nodes, edges


def _graph_measurements(
    sizes: list[int], repetitions: int
) -> list[dict[str, object]]:
    measurements: list[dict[str, object]] = []
    for node_count in sizes:
        nodes, edges = _graph_input(node_count)
        samples, result = _measure_calls(
            lambda: calculate_blast_radius(
                nodes=nodes,
                edges=edges,
                changed_services=["service-0"],
                evidence_prefix="performance-baseline",
                max_hops=node_count,
            ),
            repetitions,
        )
        measurements.append(
            {
                "contract": "app.engines.calculate_blast_radius",
                "input_nodes": node_count,
                "input_edges": len(edges),
                "reached_nodes": len(result["nodes"]),
                "iterations": repetitions,
                "repetitions": repetitions,
                "latency": _latency_summary(samples),
                "throughput_ops_per_second": _throughput(repetitions, samples),
                "output_sha256": _result_digest(result),
            }
        )
    return measurements


def _startup_measurement(samples: int) -> dict[str, object]:
    timings: list[int] = []
    successful = 0
    with TemporaryDirectory(prefix="deployguard-startup-") as directory:
        for index in range(samples):
            database_path = Path(directory) / f"startup-{index}.db"
            settings = Settings(
                app_name="DeployGuard AI",
                environment="test",
                database_url=f"sqlite:///{database_path.as_posix()}",
                seed_synthetic_data=False,
                auth_provider="development",
                otel_traces_endpoint="",
                _env_file=None,
            )
            started = perf_counter_ns()
            with TestClient(create_app(settings)) as client:
                response = client.get("/api/v1/health/live")
                successful += response.status_code == 200
                timings.append(perf_counter_ns() - started)
    return {
        "contract": "app.main.create_app + lifespan migration + GET /api/v1/health/live",
        "database": "fresh local SQLite per sample",
        "successful_samples": successful,
        "latency": _latency_summary(timings),
    }


def _job_recovery_measurement(job_count: int) -> dict[str, object]:
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    stale_locked_at = now - timedelta(minutes=10)
    with TemporaryDirectory(prefix="deployguard-recovery-") as directory:
        database_path = Path(directory) / "recovery.db"
        database = Database(f"sqlite:///{database_path.as_posix()}")
        database.migrate(allow_legacy_bootstrap=True)
        session = database.session_factory()
        try:
            session.add_all(
                [
                    BackgroundJob(
                        id=str(uuid4()),
                        job_type="performance.recovery",
                        workspace_id=None,
                        payload={"sequence": index},
                        idempotency_key=f"performance-recovery-{index}",
                        status="running",
                        attempts=1,
                        max_attempts=3,
                        available_at=stale_locked_at,
                        locked_at=stale_locked_at,
                        locked_by="terminated-worker",
                        last_error=None,
                        result=None,
                        request_id=None,
                        created_at=stale_locked_at,
                        updated_at=stale_locked_at,
                        completed_at=None,
                    )
                    for index in range(job_count)
                ]
            )
            session.commit()
            started = perf_counter_ns()
            recovered = requeue_expired_jobs(
                session,
                lease_timeout=timedelta(minutes=5),
                now=now,
            )
            elapsed = perf_counter_ns() - started
            queued = len(
                session.scalars(
                    select(BackgroundJob).where(BackgroundJob.status == "queued")
                ).all()
            )
        finally:
            session.close()
            database.dispose()
    return {
        "contract": "app.job_queue.requeue_expired_jobs",
        "database": "local SQLite",
        "stale_jobs": job_count,
        "recovered_jobs": recovered,
        "queued_after_recovery": queued,
        "latency": _latency_summary([elapsed]),
        "throughput_jobs_per_second": round(
            job_count / (elapsed / 1_000_000_000), 2
        )
        if elapsed
        else 0.0,
    }


def run_baseline(profile: str = "quick") -> dict[str, object]:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    configuration = PROFILES[profile]
    tracemalloc.start()
    try:
        risk = _risk_measurement(int(configuration["risk_iterations"]))
        graph = _graph_measurements(
            list(configuration["graph_sizes"]),
            int(configuration["graph_repetitions"]),
        )
        startup = _startup_measurement(int(configuration["startup_samples"]))
        job_recovery = _job_recovery_measurement(
            int(configuration["recovery_jobs"])
        )
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "schema": RESULT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": os.environ.get("GITHUB_SHA", "unavailable"),
        "profile": profile,
        "engine_contract": {
            "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "risk_scoring_policy_version": RISK_SCORING_POLICY_VERSION,
            "graph_version": GRAPH_VERSION,
        },
        "environment": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "unavailable",
            "logical_cpu_count": os.cpu_count(),
        },
        "methodology": {
            "clock": "time.perf_counter_ns",
            "percentile": "nearest-rank",
            "warmup": "none; cold and short-run effects are retained",
            "configuration": configuration,
        },
        "measurements": {
            "risk_engine": risk,
            "graph_engine_by_size": graph,
            "api_startup_to_liveness": startup,
            "expired_job_recovery": job_recovery,
            "python_traced_memory": {
                "scope": "entire in-process baseline run",
                "current_bytes": current_bytes,
                "peak_bytes": peak_bytes,
                "collector": "tracemalloc; Python allocations only, not process RSS",
            },
        },
        "limitations": [
            "This is a local engineering baseline, not a production SLO or capacity claim.",
            "SQLite timings do not represent PostgreSQL, network storage, or multi-instance contention.",
            "The startup sample includes app construction, migrations, lifespan entry, and liveness HTTP handling, but not container scheduling or network load balancers.",
            "Job recovery measures lease requeue persistence only; provider calls and worker scheduling are excluded.",
            "tracemalloc reports traced Python allocations and does not measure total resident memory.",
            "Short profiles prioritize regression feedback over statistically stable benchmarking.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="quick")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_baseline(args.profile)
    encoded = json.dumps(result, indent=2, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
