"""Versioned, secret-free contracts for allowlisted background jobs."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


GITHUB_CHECK_PUBLISH_JOB = "github.check.publish.v1"
_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-"
    r"(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<parent_id>[0-9a-f]{16})-"
    r"(?P<flags>[0-9a-f]{2})$"
)
_TRACESTATE_KEY_RE = re.compile(
    r"^(?:[a-z0-9][a-z0-9_\-*/]{0,255}|"
    r"[a-z0-9][a-z0-9_\-*/]{0,240}@[a-z0-9][a-z0-9_\-*/]{0,13})$"
)


class TraceContext(BaseModel):
    """A bounded W3C trace context safe to persist and log."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    traceparent: str
    tracestate: str | None = None

    @field_validator("traceparent")
    @classmethod
    def validate_traceparent(cls, value: str) -> str:
        normalized = value.strip().lower()
        match = _TRACEPARENT_RE.fullmatch(normalized)
        if (
            match is None
            or match.group("version") == "ff"
            or match.group("trace_id") == "0" * 32
            or match.group("parent_id") == "0" * 16
        ):
            raise ValueError("traceparent is not a valid W3C trace context")
        return normalized

    @field_validator("tracestate")
    @classmethod
    def validate_tracestate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 512 or any(
            ord(char) < 32 or ord(char) > 126 for char in normalized
        ):
            raise ValueError("tracestate must be printable ASCII up to 512 characters")
        members = [member.strip() for member in normalized.split(",")]
        if len(members) > 32:
            raise ValueError("tracestate cannot contain more than 32 members")
        keys: set[str] = set()
        for member in members:
            key, separator, member_value = member.partition("=")
            if (
                not separator
                or not _TRACESTATE_KEY_RE.fullmatch(key)
                or not member_value
                or len(member_value) > 256
                or member_value[0] in {" ", "\t"}
                or member_value[-1] in {" ", "\t"}
                or "," in member_value
                or "=" in member_value
                or key in keys
            ):
                raise ValueError("tracestate contains an invalid member")
            keys.add(key)
        return ",".join(members)


class GitHubCheckPublishPayload(BaseModel):
    """References needed to publish one evidence-only GitHub Check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    connection_id: str
    repository_id: str
    change_id: str
    trace_context: TraceContext | None = None

    @field_validator("connection_id", "repository_id", "change_id")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 160:
            raise ValueError("job references must contain 1 to 160 characters")
        return normalized


def validated_trace_context(
    traceparent: str | None,
    tracestate: str | None,
) -> TraceContext | None:
    """Return valid inbound trace metadata, dropping malformed input safely."""

    if not traceparent:
        return None
    try:
        return TraceContext(traceparent=traceparent, tracestate=tracestate)
    except ValueError:
        return None
