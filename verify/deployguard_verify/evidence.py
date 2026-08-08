from __future__ import annotations

import glob
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

from .models import EvidenceItem, EvidenceState


MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_FILES = 100


def _artifact_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError(f"artifact must not be a symbolic link: {path}")
    size = path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"artifact exceeds the 16 MiB limit: {path.name}")
    return path.read_bytes()


def _artifact_id(kind: str, digest: str) -> str:
    return f"{kind}-{digest[:16]}"


def _relative_source(path: Path, repository_root: Path) -> str:
    return path.relative_to(repository_root).as_posix()


def expand_artifact_patterns(repository_root: Path, patterns: list[str]) -> list[Path]:
    root = repository_root.resolve(strict=True)
    matches: dict[str, Path] = {}
    for pattern in patterns:
        if not pattern:
            continue
        candidate_pattern = str(root / pattern)
        for raw_match in glob.iglob(candidate_pattern, recursive=True):
            original = Path(raw_match)
            if original.is_symlink() or not original.is_file():
                continue
            resolved = original.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError("artifact pattern escaped the repository root")
            matches[resolved.as_posix()] = resolved
            if len(matches) > MAX_ARTIFACT_FILES:
                raise ValueError("artifact selection exceeds the 100-file limit")
    return [matches[key] for key in sorted(matches)]


def _parse_xml(raw: bytes, source: str) -> ET.Element:
    upper = raw[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError(f"XML entities are not allowed in {source}")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError(f"invalid XML artifact {source}: {error}") from error


def parse_junit(
    path: Path,
    *,
    repository_root: Path,
    source_sha: str | None,
    expected_sha: str,
) -> EvidenceItem:
    raw = _artifact_bytes(path)
    digest = hashlib.sha256(raw).hexdigest()
    root = _parse_xml(raw, path.name)
    if root.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
        raise ValueError(f"{path.name} is not a JUnit test report")
    cases = list(root.iter("testcase"))
    tests = len(cases)
    failures = sum(1 for case in cases if case.find("failure") is not None)
    errors = sum(1 for case in cases if case.find("error") is not None)
    skipped = sum(1 for case in cases if case.find("skipped") is not None)

    if source_sha != expected_sha:
        state = EvidenceState.UNKNOWN
        summary = "JUnit source SHA does not match the change head SHA."
    elif tests == 0:
        state = EvidenceState.UNKNOWN
        summary = "JUnit report contains no test cases."
    elif failures or errors:
        state = EvidenceState.FAIL
        summary = f"{failures + errors} of {tests} tests failed or errored."
    else:
        state = EvidenceState.PASS
        summary = f"{tests - skipped} tests passed; {skipped} skipped."
    return EvidenceItem(
        id=_artifact_id("tests", digest),
        kind="tests",
        state=state,
        source=_relative_source(path, repository_root),
        source_sha=source_sha,
        artifact_sha256=digest,
        summary=summary,
        metrics={
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        },
    )


def _coverage_rate(path: Path, raw: bytes) -> tuple[float, dict[str, int | float]]:
    if path.suffix.lower() == ".info" or raw.startswith(b"TN:"):
        lines_found = 0
        lines_hit = 0
        for line in raw.decode("utf-8", errors="replace").splitlines():
            if line.startswith("LF:"):
                lines_found += int(line[3:])
            elif line.startswith("LH:"):
                lines_hit += int(line[3:])
        rate = lines_hit / lines_found if lines_found else 0.0
        if lines_found < 0 or lines_hit < 0 or lines_hit > lines_found:
            raise ValueError(f"LCOV line totals are invalid in {path.name}")
        return rate, {"lines_found": lines_found, "lines_hit": lines_hit}

    root = _parse_xml(raw, path.name)
    if root.tag.rsplit("}", 1)[-1] != "coverage":
        raise ValueError(f"{path.name} is not a Cobertura coverage document")
    raw_rate = root.attrib.get("line-rate")
    if raw_rate is None:
        lines = list(root.iter("line"))
        lines_found = len(lines)
        lines_hit = sum(int(line.attrib.get("hits", "0")) > 0 for line in lines)
        rate = lines_hit / lines_found if lines_found else 0.0
        return rate, {"lines_found": lines_found, "lines_hit": lines_hit}
    rate = float(raw_rate)
    if not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError(f"coverage line-rate is invalid in {path.name}")
    return rate, {"line_rate": round(rate, 6)}


def parse_coverage(
    path: Path,
    *,
    repository_root: Path,
    source_sha: str | None,
    expected_sha: str,
) -> EvidenceItem:
    raw = _artifact_bytes(path)
    digest = hashlib.sha256(raw).hexdigest()
    rate, metrics = _coverage_rate(path, raw)
    if source_sha != expected_sha:
        state = EvidenceState.UNKNOWN
        summary = "Coverage source SHA does not match the change head SHA."
    else:
        state = EvidenceState.PASS
        summary = f"Reported line coverage is {rate:.1%}."
    return EvidenceItem(
        id=_artifact_id("coverage", digest),
        kind="coverage",
        state=state,
        source=_relative_source(path, repository_root),
        source_sha=source_sha,
        artifact_sha256=digest,
        summary=summary,
        metrics={**metrics, "line_rate": round(rate, 6)},
    )


def _sarif_severity(result: dict[str, Any], rules: dict[str, dict[str, Any]]) -> str:
    properties = result.get("properties") if isinstance(result.get("properties"), dict) else {}
    rule = rules.get(str(result.get("ruleId", "")), {})
    rule_properties = rule.get("properties") if isinstance(rule.get("properties"), dict) else {}
    raw_score = properties.get("security-severity", rule_properties.get("security-severity"))
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = None
    if score is not None and math.isfinite(score):
        if score >= 9:
            return "critical"
        if score >= 7:
            return "high"
        if score >= 4:
            return "medium"
        return "low"
    return {"error": "high", "warning": "medium", "note": "note"}.get(
        str(result.get("level", "warning")).lower(), "medium"
    )


def parse_sarif(
    path: Path,
    *,
    repository_root: Path,
    source_sha: str | None,
    expected_sha: str,
) -> EvidenceItem:
    raw = _artifact_bytes(path)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid SARIF JSON {path.name}: {error}") from error
    if not isinstance(payload, dict) or payload.get("version") != "2.1.0":
        raise ValueError(f"{path.name} is not SARIF 2.1.0")

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "note": 0}
    runs = payload.get("runs")
    if not isinstance(runs, list):
        raise ValueError(f"{path.name} SARIF runs must be a list")
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError(f"{path.name} SARIF run must be an object")
        tool = run.get("tool")
        if not isinstance(tool, dict) or not isinstance(tool.get("driver"), dict):
            raise ValueError(f"{path.name} SARIF run is missing tool.driver")
        driver = tool["driver"]
        results = run.get("results", [])
        if not isinstance(results, list):
            raise ValueError(f"{path.name} SARIF results must be a list")
        rules = {
            str(rule.get("id")): rule
            for rule in driver.get("rules", [])
            if isinstance(rule, dict) and rule.get("id")
        }
        for result in results:
            if isinstance(result, dict) and not result.get("suppressions"):
                counts[_sarif_severity(result, rules)] += 1

    total = sum(counts.values())
    if source_sha != expected_sha:
        state = EvidenceState.UNKNOWN
        summary = "SARIF source SHA does not match the change head SHA."
    elif counts["critical"] or counts["high"]:
        state = EvidenceState.FAIL
        summary = f"SARIF contains {counts['critical']} critical and {counts['high']} high findings."
    else:
        state = EvidenceState.PASS
        summary = f"SARIF contains no critical or high findings ({total} total)."
    return EvidenceItem(
        id=_artifact_id("security", digest),
        kind="security",
        state=state,
        source=_relative_source(path, repository_root),
        source_sha=source_sha,
        artifact_sha256=digest,
        summary=summary,
        metrics={**counts, "total": total},
    )


PARSERS: dict[str, Callable[..., EvidenceItem]] = {
    "tests": parse_junit,
    "coverage": parse_coverage,
    "security": parse_sarif,
}


def collect_artifacts(
    repository_root: Path,
    *,
    patterns: dict[str, list[str]],
    source_sha: str | None,
    expected_sha: str,
    build_status: str,
) -> tuple[EvidenceItem, ...]:
    items: list[EvidenceItem] = []
    for kind in ("tests", "coverage", "security"):
        for path in expand_artifact_patterns(repository_root, patterns.get(kind, [])):
            items.append(
                PARSERS[kind](
                    path,
                    repository_root=repository_root,
                    source_sha=source_sha,
                    expected_sha=expected_sha,
                )
            )

    if build_status != "unknown":
        if source_sha != expected_sha:
            state = EvidenceState.UNKNOWN
            summary = "Build source SHA does not match the change head SHA."
        else:
            state = EvidenceState.PASS if build_status == "success" else EvidenceState.FAIL
            summary = f"Build status was reported as {build_status}."
        items.append(
            EvidenceItem(
                id=f"build-{expected_sha[:16]}",
                kind="build",
                state=state,
                source="ci:build-status",
                source_sha=source_sha,
                artifact_sha256=None,
                summary=summary,
                metrics={"status": build_status},
            )
        )
    return tuple(sorted(items, key=lambda item: (item.kind, item.source, item.id)))
