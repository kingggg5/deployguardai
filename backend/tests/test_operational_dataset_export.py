from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPORTER_PATH = REPOSITORY_ROOT / "scripts" / "export_operational_dataset.py"


def _load_exporter() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "deployguard_operational_dataset_exporter", EXPORTER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load operational dataset exporter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPORTER = _load_exporter()


def test_export_is_deterministic_and_invokes_production_ranker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    real_ranker = EXPORTER.rank_hypotheses

    def observed_ranker(**kwargs: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return real_ranker(**kwargs)

    monkeypatch.setattr(EXPORTER, "rank_hypotheses", observed_ranker)
    first_examples, first_manifest = EXPORTER.build_dataset()
    second_examples, second_manifest = EXPORTER.build_dataset()

    assert calls == len(first_examples) + len(second_examples)
    assert first_examples == second_examples
    assert first_manifest == second_manifest
    assert first_manifest["total_examples"] == 3
    assert first_manifest["evaluation_eligible_examples"] == 2
    assert first_manifest["training_eligible_examples"] == 0
    assert first_manifest["splits"] == {"development": 2, "unverified": 1}


def test_examples_preserve_graph_references_and_truth_boundaries() -> None:
    examples, _ = EXPORTER.build_dataset()

    for example in examples:
        EXPORTER.validate_example(example)
        evidence_ids = {item["id"] for item in example["evidence"]}
        assert example["data_mode"] == "synthetic"
        assert example["ground_truth"]["human_verdict"] is None
        assert example["quality"]["evidence_reference_integrity"] == 1.0
        assert not example["quality"]["training_eligible"]
        for hypothesis in example["hypotheses"]:
            assert set(hypothesis["evidence_ids"]).issubset(evidence_ids)
            assert set(hypothesis["counter_evidence_ids"]).issubset(evidence_ids)

    unverified = next(item for item in examples if item["split"] == "unverified")
    assert unverified["ground_truth"]["hypothesis_id"] is None
    assert not unverified["quality"]["evaluation_eligible"]


def test_public_seed_excludes_identity_and_credential_fields() -> None:
    examples, _ = EXPORTER.build_dataset()
    keys = set(EXPORTER._walk_keys(examples))

    assert EXPORTER.PROHIBITED_PUBLIC_KEYS.isdisjoint(keys)


def test_bundle_hashes_and_check_mode_detect_drift(tmp_path: Path) -> None:
    manifest = EXPORTER.write_bundle(tmp_path)
    examples_path = tmp_path / "examples.jsonl"
    manifest_path = tmp_path / "manifest.json"

    assert examples_path.is_file()
    assert manifest_path.is_file()
    parsed = [json.loads(line) for line in examples_path.read_text().splitlines()]
    assert len(parsed) == manifest["total_examples"]
    assert EXPORTER.write_bundle(tmp_path, check=True) == manifest

    examples_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dataset artifact drift"):
        EXPORTER.write_bundle(tmp_path, check=True)


def test_connected_or_human_claims_fail_closed() -> None:
    examples, _ = EXPORTER.build_dataset()
    connected = dict(examples[0])
    connected["data_mode"] = "connected"
    with pytest.raises(ValueError, match="synthetic data only"):
        EXPORTER.validate_example(connected)

    false_human_claim = dict(examples[0])
    false_human_claim["ground_truth"] = {
        **examples[0]["ground_truth"],
        "human_verdict": {
            "verdict": "confirmed",
            "hypothesis_id": examples[0]["hypotheses"][0]["id"],
            "note": "not actually collected",
        },
    }
    with pytest.raises(ValueError, match="must not claim a human verdict"):
        EXPORTER.validate_example(false_human_claim)
