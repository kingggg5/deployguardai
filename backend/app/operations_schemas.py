import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .schemas import TimelineEvent


NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
ResourceId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
Tag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]
ServiceTier = Literal["tier_1", "tier_2", "tier_3", "tier_4"]
ServiceLifecycle = Literal["active", "deprecated", "experimental"]
EventSeverity = Literal["debug", "info", "warning", "error", "critical"]
IngestionStatus = Literal["accepted", "correlated"]
IncidentStatus = Literal[
    "open", "acknowledged", "investigating", "mitigated", "resolved"
]
IncidentSeverity = Literal["sev1", "sev2", "sev3", "sev4"]
BackgroundJobStatus = Literal[
    "queued", "running", "succeeded", "failed", "dead_letter"
]


class BackgroundJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    job_type: str
    workspace_id: str
    status: BackgroundJobStatus
    attempts: int
    max_attempts: int
    request_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class OperationsModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ServiceCreate(OperationsModel):
    name: NonEmptyString = Field(max_length=160)
    slug: NonEmptyString = Field(
        max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    description: str = Field(default="", max_length=4_000)
    tier: ServiceTier = "tier_2"
    lifecycle: ServiceLifecycle = "active"
    owner_team: NonEmptyString = Field(max_length=160)
    repository_id: str | None = Field(default=None, max_length=36)
    dependencies: list[ResourceId] = Field(default_factory=list, max_length=100)
    runbook_url: str | None = Field(default=None, max_length=2_048)
    tags: list[Tag] = Field(default_factory=list, max_length=50)

    @field_validator("dependencies", "tags")
    @classmethod
    def unique_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("runbook_url")
    @classmethod
    def validate_runbook_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("runbook_url must use http or https")
        return normalized


class ServiceUpdate(OperationsModel):
    name: NonEmptyString | None = Field(default=None, max_length=160)
    slug: NonEmptyString | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = Field(default=None, max_length=4_000)
    tier: ServiceTier | None = None
    lifecycle: ServiceLifecycle | None = None
    owner_team: NonEmptyString | None = Field(default=None, max_length=160)
    repository_id: str | None = Field(default=None, max_length=36)
    dependencies: list[ResourceId] | None = Field(
        default=None, max_length=100
    )
    runbook_url: str | None = Field(default=None, max_length=2_048)
    tags: list[Tag] | None = Field(default=None, max_length=50)

    @field_validator("dependencies", "tags")
    @classmethod
    def unique_optional_values(
        cls, values: list[str] | None
    ) -> list[str] | None:
        return list(dict.fromkeys(values)) if values is not None else None

    @field_validator("runbook_url")
    @classmethod
    def validate_runbook_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("runbook_url must use http or https")
        return normalized

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ServiceUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        non_nullable = {
            "name",
            "slug",
            "description",
            "tier",
            "lifecycle",
            "owner_team",
            "dependencies",
            "tags",
        }
        invalid = [
            field
            for field in non_nullable
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if invalid:
            raise ValueError(
                f"{', '.join(sorted(invalid))} cannot be null"
            )
        return self


class ServiceResponse(OperationsModel):
    id: str
    workspace_id: str
    name: str
    slug: str
    description: str
    tier: ServiceTier
    lifecycle: ServiceLifecycle
    owner_team: str
    repository_id: str | None
    dependencies: list[str]
    runbook_url: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class RiskPolicyUpdate(OperationsModel):
    enabled: bool
    warn_threshold: int = Field(ge=0, le=100)
    block_threshold: int = Field(ge=0, le=100)
    require_tests: bool
    require_rollback: bool
    max_blast_radius: int = Field(ge=1, le=10_000)
    version: int = Field(ge=2)

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> "RiskPolicyUpdate":
        if self.warn_threshold >= self.block_threshold:
            raise ValueError("warn_threshold must be lower than block_threshold")
        return self


class RiskPolicyResponse(RiskPolicyUpdate):
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class OperationalEventCreate(OperationsModel):
    provider_event_id: NonEmptyString = Field(max_length=160)
    repository_id: str | None = Field(default=None, max_length=36)
    service_id: str | None = Field(default=None, max_length=36)
    incident_id: str | None = Field(default=None, max_length=80)
    source: NonEmptyString = Field(max_length=100)
    event_type: NonEmptyString = Field(max_length=100)
    occurred_at: datetime
    severity: EventSeverity = "info"
    summary: NonEmptyString = Field(max_length=1_000)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        now = datetime.now(UTC)
        normalized = value.astimezone(UTC)
        if normalized > now + timedelta(minutes=5):
            raise ValueError(
                "occurred_at cannot be more than 5 minutes in the future"
            )
        if normalized < now - timedelta(days=366):
            raise ValueError(
                "occurred_at cannot be more than 366 days in the past"
            )
        return value

    @field_validator("attributes", "provenance")
    @classmethod
    def bound_structured_payload(
        cls, value: dict[str, Any]
    ) -> dict[str, Any]:
        if len(value) > 100:
            raise ValueError("structured payload cannot exceed 100 top-level keys")
        try:
            serialized = json.dumps(
                value, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "structured payload must be JSON serializable"
            ) from exc
        if len(serialized) > 65_536:
            raise ValueError("structured payload cannot exceed 64 KiB")
        return value


class ManualOperationalEventCreate(OperationalEventCreate):
    @field_validator("provenance", mode="before")
    @classmethod
    def discard_client_provenance(
        cls, _value: object
    ) -> dict[str, Any]:
        # Provenance is a server-owned trust statement. The member endpoint
        # accepts the legacy field for compatibility but never persists it.
        if not isinstance(_value, dict):
            raise ValueError("provenance must be an object")
        if len(_value) > 100:
            raise ValueError(
                "structured payload cannot exceed 100 top-level keys"
            )
        serialized = json.dumps(
            _value, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if len(serialized) > 65_536:
            raise ValueError("structured payload cannot exceed 64 KiB")
        return {}


class OperationalEventResponse(OperationsModel):
    id: str
    provider_event_id: str
    workspace_id: str
    repository_id: str | None
    service_id: str | None
    incident_id: str | None
    source: str
    event_type: str
    occurred_at: datetime
    severity: EventSeverity
    summary: str
    attributes: dict[str, Any]
    provenance: dict[str, Any]
    ingestion_status: IngestionStatus
    ingested_at: datetime


class IncidentLifecycleUpdate(OperationsModel):
    status: IncidentStatus | None = None
    assignee_user_id: str | None = Field(default=None, max_length=36)
    severity: IncidentSeverity | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "IncidentLifecycleUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for field in ("status", "severity"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class IncidentLifecycleResponse(OperationsModel):
    incident_id: str
    workspace_id: str
    status: IncidentStatus
    severity: IncidentSeverity
    assignee_user_id: str | None
    resolved_at: datetime | None
    timeline: list[TimelineEvent]


class IncidentNoteCreate(OperationsModel):
    note: NonEmptyString = Field(max_length=4_000)


class NotificationResponse(OperationsModel):
    id: str
    workspace_id: str
    user_id: str
    kind: Literal["incident_lifecycle", "incident_note"]
    title: str
    message: str
    resource_type: str
    resource_id: str
    read_at: datetime | None
    created_at: datetime
