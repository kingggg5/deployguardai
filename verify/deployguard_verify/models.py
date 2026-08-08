from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Decision(StrEnum):
    PASS = "pass"
    REVIEW = "review"
    BLOCK = "block"
    ERROR = "error"


class EvidenceState(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    kind: str
    state: EvidenceState
    source: str
    source_sha: str | None
    artifact_sha256: str | None
    summary: str
    metrics: dict[str, int | float | str | bool | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


@dataclass(frozen=True)
class GitChange:
    repository: str
    base_sha: str
    head_sha: str
    merge_base_sha: str
    generated_at: str
    paths: tuple[str, ...]
    files_changed: int
    lines_added: int
    lines_deleted: int
    flags: tuple[str, ...]

    @property
    def docs_only(self) -> bool:
        return bool(self.paths) and all(
            path.lower().endswith((".md", ".mdx", ".rst", ".txt"))
            or path.lower().startswith("docs/")
            for path in self.paths
        )


@dataclass(frozen=True)
class VerificationResult:
    decision: Decision
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    receipt: dict[str, Any]
