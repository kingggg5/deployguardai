from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema

from deployguard_verify.cli import main


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.email", "verify@example.invalid")
    _git(root, "config", "user.name", "DeployGuard Verify")
    (root / ".deployguard").mkdir()
    (root / ".deployguard" / "policy.yml").write_text(
        """schema_version: deployguard-policy/v0.1
requirements:
  tests:
    required: true
    skip_for_docs_only: true
  build:
    required: false
  coverage:
    required: false
    minimum_line_rate: 0.0
  security:
    required: false
    block_severities: [critical, high]
path_rules: []
""",
        encoding="utf-8",
    )
    (root / "example.py").write_text("value = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    base_sha = _git(root, "rev-parse", "HEAD")
    (root / "example.py").write_text("value = 2\n", encoding="utf-8")
    _git(root, "add", "example.py")
    _git(root, "commit", "-m", "change")
    return root, base_sha, _git(root, "rev-parse", "HEAD")


def _junit(root: Path, failing: bool = False) -> Path:
    path = root / "artifacts" / "junit.xml"
    path.parent.mkdir()
    failure = "<failure/>" if failing else ""
    path.write_text(
        f"<testsuite><testcase name='verify'>{failure}</testcase></testsuite>",
        encoding="utf-8",
    )
    return path


def test_cli_writes_byte_identical_receipt_for_same_inputs(tmp_path: Path) -> None:
    root, base_sha, head_sha = _repository(tmp_path)
    _junit(root)
    arguments = [
        "verify",
        "--repository-root",
        str(root),
        "--repository",
        "example/repository",
        "--base",
        base_sha,
        "--head",
        head_sha,
        "--evidence-sha",
        head_sha,
        "--junit",
        "artifacts/junit.xml",
    ]

    output = root / ".deployguard" / "artifacts" / "evidence-receipt.json"
    replays: list[bytes] = []
    for _ in range(10):
        assert main(arguments) == 0
        replays.append(output.read_bytes())

    assert all(replay == replays[0] for replay in replays)
    first = replays[0]
    receipt = json.loads(first)
    schema_path = Path(__file__).resolve().parents[1] / "schema" / "evidence-receipt-v0.1.schema.json"
    jsonschema.Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=jsonschema.FormatChecker(),
    ).validate(receipt)
    assert receipt["decision"]["status"] == "pass"
    assert receipt["policy"]["source"].startswith("git:")
    assert not any(str(root) in json.dumps(item) for item in receipt["evidence"])


def test_cli_returns_review_for_sha_mismatch(tmp_path: Path) -> None:
    root, base_sha, head_sha = _repository(tmp_path)
    _junit(root)

    exit_code = main(
        [
            "verify",
            "--repository-root",
            str(root),
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--evidence-sha",
            base_sha,
            "--junit",
            "artifacts/junit.xml",
        ]
    )

    assert exit_code == 2


def test_cli_rejects_non_exact_evidence_revision(tmp_path: Path) -> None:
    root, base_sha, head_sha = _repository(tmp_path)
    _junit(root)

    exit_code = main(
        [
            "verify",
            "--repository-root",
            str(root),
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--evidence-sha",
            "HEAD",
            "--junit",
            "artifacts/junit.xml",
        ]
    )

    assert exit_code == 4


def test_cli_returns_block_for_failed_tests(tmp_path: Path) -> None:
    root, base_sha, head_sha = _repository(tmp_path)
    _junit(root, failing=True)

    exit_code = main(
        [
            "verify",
            "--repository-root",
            str(root),
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--evidence-sha",
            head_sha,
            "--junit",
            "artifacts/junit.xml",
        ]
    )

    assert exit_code == 3


def test_init_does_not_overwrite_existing_policy(tmp_path: Path) -> None:
    policy = tmp_path / ".deployguard" / "policy.yml"
    policy.parent.mkdir()
    policy.write_text("owned by user\n", encoding="utf-8")

    assert main(["init", "--repository-root", str(tmp_path), "--github"]) == 0

    assert policy.read_text(encoding="utf-8") == "owned by user\n"
    assert (tmp_path / ".github" / "workflows" / "deployguard.yml").exists()
