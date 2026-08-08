from __future__ import annotations

import json
from pathlib import Path

import pytest

from deployguard_verify.evidence import (
    collect_artifacts,
    expand_artifact_patterns,
    parse_coverage,
    parse_junit,
    parse_sarif,
)


HEAD_SHA = "b" * 40


def test_junit_failure_is_observed_without_log_content(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        "<testsuite><testcase name='ok'/><testcase name='bad'><failure>secret log</failure></testcase></testsuite>",
        encoding="utf-8",
    )

    item = parse_junit(
        report,
        repository_root=tmp_path,
        source_sha=HEAD_SHA,
        expected_sha=HEAD_SHA,
    )

    assert item.state.value == "fail"
    assert item.metrics == {"tests": 2, "failures": 1, "errors": 0, "skipped": 0}
    assert "secret log" not in str(item.to_dict())


def test_sha_mismatch_is_unknown_even_when_tests_pass(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text("<testsuite><testcase name='ok'/></testsuite>", encoding="utf-8")

    item = parse_junit(
        report,
        repository_root=tmp_path,
        source_sha="a" * 40,
        expected_sha=HEAD_SHA,
    )

    assert item.state.value == "unknown"


def test_cobertura_and_lcov_are_normalized(tmp_path: Path) -> None:
    cobertura = tmp_path / "coverage.xml"
    cobertura.write_text("<coverage line-rate='0.875'/>", encoding="utf-8")
    lcov = tmp_path / "lcov.info"
    lcov.write_text("TN:\nLF:10\nLH:8\nend_of_record\n", encoding="utf-8")

    xml_item = parse_coverage(
        cobertura,
        repository_root=tmp_path,
        source_sha=HEAD_SHA,
        expected_sha=HEAD_SHA,
    )
    lcov_item = parse_coverage(
        lcov,
        repository_root=tmp_path,
        source_sha=HEAD_SHA,
        expected_sha=HEAD_SHA,
    )

    assert xml_item.metrics["line_rate"] == 0.875
    assert lcov_item.metrics["line_rate"] == 0.8


def test_non_cobertura_xml_is_rejected(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.xml"
    coverage.write_text("<report line-rate='1'/>", encoding="utf-8")

    with pytest.raises(ValueError, match="not a Cobertura"):
        parse_coverage(
            coverage,
            repository_root=tmp_path,
            source_sha=HEAD_SHA,
            expected_sha=HEAD_SHA,
        )


def test_sarif_security_severity_is_normalized(tmp_path: Path) -> None:
    sarif = tmp_path / "results.sarif"
    sarif.write_text(
        json.dumps(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "tool": {
                            "driver": {
                                "name": "fixture",
                                "rules": [
                                    {
                                        "id": "danger",
                                        "properties": {"security-severity": "9.2"},
                                    }
                                ],
                            }
                        },
                        "results": [{"ruleId": "danger", "level": "error"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    item = parse_sarif(
        sarif,
        repository_root=tmp_path,
        source_sha=HEAD_SHA,
        expected_sha=HEAD_SHA,
    )

    assert item.state.value == "fail"
    assert item.metrics["critical"] == 1


def test_malformed_sarif_shape_is_rejected(tmp_path: Path) -> None:
    sarif = tmp_path / "results.sarif"
    sarif.write_text(
        json.dumps({"version": "2.1.0", "runs": {"not": "a-list"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="runs must be a list"):
        parse_sarif(
            sarif,
            repository_root=tmp_path,
            source_sha=HEAD_SHA,
            expected_sha=HEAD_SHA,
        )


def test_xml_entities_are_rejected(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        "<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><testsuite/>",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="XML entities"):
        parse_junit(
            report,
            repository_root=tmp_path,
            source_sha=HEAD_SHA,
            expected_sha=HEAD_SHA,
        )


def test_artifact_glob_deduplicates_matches(tmp_path: Path) -> None:
    report = tmp_path / "artifacts" / "junit.xml"
    report.parent.mkdir()
    report.write_text("<testsuite/>", encoding="utf-8")

    matches = expand_artifact_patterns(tmp_path, ["**/*.xml", "artifacts/junit.xml"])

    assert matches == [report.resolve()]


def test_build_status_with_mismatched_sha_is_unknown(tmp_path: Path) -> None:
    items = collect_artifacts(
        tmp_path,
        patterns={},
        source_sha="a" * 40,
        expected_sha=HEAD_SHA,
        build_status="success",
    )

    assert items[0].kind == "build"
    assert items[0].state.value == "unknown"
