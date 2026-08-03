from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVALUATOR_PATH = REPOSITORY_ROOT / "scripts" / "evaluate_benchmarks.py"


def _load_evaluator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "deployguard_benchmark_evaluator", EVALUATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load benchmark evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATOR = _load_evaluator()


def _manifest() -> dict[str, object]:
    return json.loads(EVALUATOR.DEFAULT_MANIFEST.read_text(encoding="utf-8"))


def _write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def test_evaluator_invokes_real_engine_and_derives_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    real_ranker = EVALUATOR.rank_hypotheses

    def observed_ranker(**kwargs: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return real_ranker(**kwargs)

    monkeypatch.setattr(EVALUATOR, "rank_hypotheses", observed_ranker)
    first = EVALUATOR.run_benchmark_eval()
    second = EVALUATOR.run_benchmark_eval()

    assert calls == first["total_episodes"] + second["total_episodes"]
    assert first == second
    assert first["engine_contract"] == "app.engines.rank_hypotheses"
    assert first["top_1_accuracy"] == 0.8
    assert first["top_3_accuracy"] == 1.0
    assert first["mean_reciprocal_rank_mrr"] == 0.9
    assert first["evidence_reference_integrity"] == 1.0
    assert first["unsupported_claims_rate"] is None
    assert first["unsupported_claims_status"] == "not_measured_requires_human_review"
    assert len(first["failure_cases"]) == 1


def test_manifest_contains_inputs_and_labels_not_precomputed_outputs() -> None:
    payload = _manifest()

    for episode in payload["episodes"]:
        assert EVALUATOR.LEGACY_OUTPUT_FIELDS.isdisjoint(episode)
        assert episode["input"]["evidence"]
        assert episode["input"]["candidates"]
        assert episode["expected"]["root_cause_candidate_id"]


def test_changed_evidence_changes_engine_derived_rank(tmp_path: Path) -> None:
    baseline = EVALUATOR.run_benchmark_eval()
    payload = _manifest()
    episode = payload["episodes"][0]
    alternative_id = "ep-001-fraud"
    for evidence in episode["input"]["evidence"]:
        evidence["supports"] = [alternative_id]
        evidence["contradicts"] = []

    changed = EVALUATOR.run_benchmark_eval(_write_manifest(tmp_path, payload))

    baseline_episode = baseline["episodes"][0]
    changed_episode = changed["episodes"][0]
    assert baseline_episode["prediction_candidate_id"] == "ep-001-payment"
    assert changed_episode["prediction_candidate_id"] == alternative_id
    assert changed_episode["expected_rank"] > baseline_episode["expected_rank"]


def test_legacy_precomputed_output_is_rejected(tmp_path: Path) -> None:
    payload = _manifest()
    payload["episodes"][0]["prediction"] = "payment-adapter"

    with pytest.raises(ValueError, match="must not contain engine outputs"):
        EVALUATOR.run_benchmark_eval(_write_manifest(tmp_path, payload))


@pytest.mark.parametrize("mutation", ["duplicate_evidence", "nonfinite_prior", "unknown_label"])
def test_malformed_episode_fails_closed(tmp_path: Path, mutation: str) -> None:
    payload = copy.deepcopy(_manifest())
    episode = payload["episodes"][0]
    if mutation == "duplicate_evidence":
        episode["input"]["evidence"][1]["id"] = episode["input"]["evidence"][0]["id"]
    elif mutation == "nonfinite_prior":
        episode["input"]["candidates"][0]["prior"] = float("nan")
    else:
        episode["expected"]["root_cause_candidate_id"] = "not-a-candidate"

    with pytest.raises(ValueError):
        EVALUATOR.run_benchmark_eval(_write_manifest(tmp_path, payload))
