from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .models import GitChange
from .policy import LoadedPolicy, parse_policy


GIT_TIMEOUT_SECONDS = 20
ZERO_SHA = "0" * 40


class GitError(RuntimeError):
    pass


def _git(repository_root: Path, *args: str, allow_failure: bool = False) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        if allow_failure:
            return None
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown git error"
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def resolve_commit(repository_root: Path, revision: str) -> str:
    if not revision or revision == ZERO_SHA:
        raise GitError("a non-zero base and head revision are required")
    resolved = _git(repository_root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    assert resolved is not None
    return resolved.strip().lower()


def _repository_name(repository_root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    remote = _git(repository_root, "config", "--get", "remote.origin.url", allow_failure=True)
    if remote:
        value = remote.strip().removesuffix(".git")
        ssh_match = re.search(r"github\.com[:/]([^/]+/[^/]+)$", value)
        if ssh_match:
            return ssh_match.group(1)
        return value.rsplit("/", 2)[-2] + "/" + value.rsplit("/", 1)[-1]
    return repository_root.name


def _change_flags(paths: tuple[str, ...]) -> tuple[str, ...]:
    flags: set[str] = set()
    lowered = [path.lower() for path in paths]
    if paths and all(
        path.endswith((".md", ".mdx", ".rst", ".txt")) or path.startswith("docs/")
        for path in lowered
    ):
        flags.add("docs-only")
    if any("/migrations/" in f"/{path}" or path.endswith(".sql") for path in lowered):
        flags.add("database-migration")
    if any("/auth/" in f"/{path}" or "security" in path for path in lowered):
        flags.add("auth-or-security-change")
    if any(path.startswith(".github/workflows/") for path in lowered):
        flags.add("ci-workflow-change")
    if any(
        path.endswith(("dockerfile", ".yml", ".yaml", ".toml", ".json"))
        for path in lowered
    ):
        flags.add("configuration-change")
    if any(
        path.endswith(
            (
                "requirements.txt",
                "requirements-prod.txt",
                "pyproject.toml",
                "package.json",
                "package-lock.json",
                ".csproj",
            )
        )
        for path in lowered
    ):
        flags.add("dependency-change")
    return tuple(sorted(flags))


def collect_git_change(
    repository_root: Path,
    *,
    base_revision: str,
    head_revision: str,
    repository: str | None = None,
) -> GitChange:
    root = repository_root.resolve(strict=True)
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != "true":
        raise GitError(f"{root} is not a Git work tree")

    base_sha = resolve_commit(root, base_revision)
    head_sha = resolve_commit(root, head_revision)
    merge_base = _git(root, "merge-base", base_sha, head_sha)
    if not merge_base:
        raise GitError("base and head do not share a merge base")
    merge_base_sha = merge_base.strip().lower()

    raw_paths = _git(root, "diff", "--name-only", "-z", merge_base_sha, head_sha) or ""
    paths = tuple(sorted(path.replace("\\", "/") for path in raw_paths.split("\0") if path))

    raw_numstat = _git(root, "diff", "--numstat", merge_base_sha, head_sha) or ""
    lines_added = 0
    lines_deleted = 0
    for line in raw_numstat.splitlines():
        fields = line.split("\t", 2)
        if len(fields) < 2:
            continue
        if fields[0].isdigit():
            lines_added += int(fields[0])
        if fields[1].isdigit():
            lines_deleted += int(fields[1])

    generated_at = _git(root, "show", "-s", "--format=%cI", head_sha)
    if not generated_at:
        raise GitError("head commit does not have a commit timestamp")

    return GitChange(
        repository=_repository_name(root, repository),
        base_sha=base_sha,
        head_sha=head_sha,
        merge_base_sha=merge_base_sha,
        generated_at=generated_at.strip(),
        paths=paths,
        files_changed=len(paths),
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        flags=_change_flags(paths),
    )


def load_policy_from_base(
    repository_root: Path,
    *,
    base_sha: str,
    policy_path: str,
) -> LoadedPolicy | None:
    normalized = Path(policy_path).as_posix().lstrip("/")
    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError("policy path must remain inside the repository")
    raw = subprocess.run(
        ["git", "show", f"{base_sha}:{normalized}"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if raw.returncode != 0:
        return None
    return parse_policy(raw.stdout, source=f"git:{base_sha}:{normalized}")
