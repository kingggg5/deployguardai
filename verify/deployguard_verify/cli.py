from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Sequence

import yaml

from .engine import VERIFY_ENGINE_VERSION, verify_change
from .evidence import collect_artifacts
from .git_change import GitError, collect_git_change, load_policy_from_base
from .models import Decision, VerificationResult
from .policy import DEFAULT_POLICY, builtin_policy, load_working_tree_policy


EXIT_CODES = {
    Decision.PASS: 0,
    Decision.REVIEW: 2,
    Decision.BLOCK: 3,
    Decision.ERROR: 4,
}

DEFAULT_POLICY_PATH = ".deployguard/policy.yml"
DEFAULT_RECEIPT_PATH = ".deployguard/artifacts/evidence-receipt.json"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _markdown_summary(result: VerificationResult) -> str:
    receipt = result.receipt
    evidence = receipt["evidence"]
    lines = [
        "## DeployGuard Evidence Receipt",
        "",
        f"**Decision:** `{result.decision.value.upper()}`  ",
        f"**Head:** `{receipt['repository']['head_sha']}`  ",
        f"**Receipt:** `{receipt['receipt_sha256']}`",
        "",
        "### Reasons",
        "",
    ]
    lines.extend(f"- `{code}` — {reason}" for code, reason in zip(result.reason_codes, result.reasons))
    lines.extend(["", "### Evidence", ""])
    if evidence:
        lines.extend(
            f"- `{item['kind']}` / `{item['state'].upper()}` — {item['summary']}"
            for item in evidence
        )
    else:
        lines.append("- No evidence artifacts were supplied.")
    lines.append("")
    return "\n".join(lines)


def _append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _verify(args: argparse.Namespace) -> int:
    repository_root = Path(args.repository_root).resolve(strict=True)
    change = collect_git_change(
        repository_root,
        base_revision=args.base,
        head_revision=args.head,
        repository=args.repository,
    )
    if args.policy_source == "base":
        policy = load_policy_from_base(
            repository_root,
            base_sha=change.base_sha,
            policy_path=args.policy,
        ) or builtin_policy()
    elif args.policy_source == "working-tree":
        policy = load_working_tree_policy(repository_root, args.policy)
    else:
        policy = builtin_policy()

    source_sha = args.evidence_sha or os.environ.get("DEPLOYGUARD_EVIDENCE_SHA")
    if source_sha:
        source_sha = source_sha.lower()
    else:
        source_sha = change.head_sha
    if re.fullmatch(r"[0-9a-f]{40,64}", source_sha) is None:
        raise ValueError("evidence SHA must be an exact 40-64 character hexadecimal commit ID")
    evidence = collect_artifacts(
        repository_root,
        patterns={
            "tests": args.junit,
            "coverage": args.coverage,
            "security": args.sarif,
        },
        source_sha=source_sha,
        expected_sha=change.head_sha,
        build_status=args.build_status,
    )
    result = verify_change(change=change, policy=policy, evidence=evidence)

    output_path = (repository_root / args.output).resolve()
    if not output_path.is_relative_to(repository_root):
        raise ValueError("receipt output must remain inside the repository")
    _write_json(output_path, result.receipt)
    summary = _markdown_summary(result)
    if args.github_summary:
        _append_text(Path(args.github_summary), summary)
    if args.github_output:
        _append_text(
            Path(args.github_output),
            "\n".join(
                [
                    f"decision={result.decision.value}",
                    f"receipt_sha256={result.receipt['receipt_sha256']}",
                    f"receipt_path={output_path.relative_to(repository_root).as_posix()}",
                    "",
                ]
            ),
        )
    if args.json:
        print(json.dumps(result.receipt, ensure_ascii=False, sort_keys=True))
    else:
        print(summary)
        print(f"Receipt written to {output_path.relative_to(repository_root).as_posix()}")
    return EXIT_CODES[result.decision]


POLICY_TEMPLATE = yaml.safe_dump(
    DEFAULT_POLICY,
    sort_keys=False,
    allow_unicode=True,
)

WORKFLOW_TEMPLATE = """name: DeployGuard Verify

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  evidence-receipt:
    name: Evidence receipt
    runs-on: ubuntu-latest
    steps:
      - name: Check out the pull request head
        uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false

      # Run your repository's tests here and write JUnit XML. Until this is
      # configured, DeployGuard deliberately returns REVIEW rather than PASS.

      - name: Verify change evidence
        uses: kingggg5/deployguardai@v1
        with:
          base-sha: ${{ github.event.pull_request.base.sha }}
          head-sha: ${{ github.event.pull_request.head.sha }}
          evidence-sha: ${{ github.event.pull_request.head.sha }}
          junit: path/to/junit.xml
"""

AGENTS_SNIPPET = """<!-- deployguard:start -->
## DeployGuard change safety

Before declaring a change ready, run `deployguard verify` against the protected
base revision and cite the generated receipt ID. Never invent test, coverage,
security, or deployment evidence. Treat missing or SHA-mismatched evidence as
UNKNOWN/REVIEW. Do not merge, deploy, roll back, or change a DeployGuard decision
without verified evidence and explicit human authorization.
<!-- deployguard:end -->
"""


def _create_file(path: Path, content: str, *, force: bool) -> str:
    if path.exists() and not force:
        return f"kept existing {path.as_posix()}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return f"created {path.as_posix()}"


def _safe_init_target(root: Path, relative_path: str) -> Path:
    candidate = root / relative_path
    if candidate.is_symlink():
        raise ValueError(f"initializer target must not be a symbolic link: {relative_path}")
    existing_parent = candidate.parent
    while not existing_parent.exists() and existing_parent != root:
        existing_parent = existing_parent.parent
    resolved_parent = existing_parent.resolve(strict=True)
    if not resolved_parent.is_relative_to(root):
        raise ValueError(f"initializer target escaped the repository: {relative_path}")
    return candidate


def _init(args: argparse.Namespace) -> int:
    root = Path(args.repository_root).resolve(strict=True)
    messages = [
        _create_file(
            _safe_init_target(root, DEFAULT_POLICY_PATH),
            POLICY_TEMPLATE,
            force=args.force,
        )
    ]
    if args.github:
        messages.append(
            _create_file(
                _safe_init_target(root, ".github/workflows/deployguard.yml"),
                WORKFLOW_TEMPLATE,
                force=args.force,
            )
        )
    if args.agent == "codex":
        agents_path = _safe_init_target(root, "AGENTS.md")
        existing = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
        if "<!-- deployguard:start -->" not in existing:
            separator = "\n" if existing and not existing.endswith("\n\n") else ""
            agents_path.write_text(
                existing + separator + AGENTS_SNIPPET,
                encoding="utf-8",
                newline="\n",
            )
            messages.append("added DeployGuard guidance to AGENTS.md")
        else:
            messages.append("kept existing DeployGuard guidance in AGENTS.md")
    print("\n".join(messages))
    if args.github:
        print(
            "The generated workflow fails closed with REVIEW until its JUnit path is configured."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deployguard",
        description="Create deterministic, keyless evidence receipts for software changes.",
    )
    parser.add_argument("--version", action="version", version=VERIFY_ENGINE_VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify", help="verify a Git change")
    verify_parser.add_argument("--repository-root", default=".")
    verify_parser.add_argument("--repository")
    verify_parser.add_argument("--base", default=os.environ.get("DEPLOYGUARD_BASE_SHA", "HEAD^"))
    verify_parser.add_argument("--head", default=os.environ.get("DEPLOYGUARD_HEAD_SHA", "HEAD"))
    verify_parser.add_argument("--evidence-sha")
    verify_parser.add_argument("--policy", default=DEFAULT_POLICY_PATH)
    verify_parser.add_argument(
        "--policy-source",
        choices=("base", "working-tree", "builtin"),
        default="base",
        help="read policy from the protected base commit by default",
    )
    verify_parser.add_argument("--junit", action="append", default=[])
    verify_parser.add_argument("--coverage", action="append", default=[])
    verify_parser.add_argument("--sarif", action="append", default=[])
    verify_parser.add_argument(
        "--build-status", choices=("success", "failure", "unknown"), default="unknown"
    )
    verify_parser.add_argument("--output", default=DEFAULT_RECEIPT_PATH)
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.add_argument("--github-summary")
    verify_parser.add_argument("--github-output")
    verify_parser.set_defaults(handler=_verify)

    init_parser = subparsers.add_parser("init", help="scaffold repository integration")
    init_parser.add_argument("--repository-root", default=".")
    init_parser.add_argument("--github", action="store_true")
    init_parser.add_argument("--agent", choices=("none", "codex"), default="none")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=_init)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (GitError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"DeployGuard verification error: {error}", file=sys.stderr)
        return EXIT_CODES[Decision.ERROR]


if __name__ == "__main__":
    raise SystemExit(main())
