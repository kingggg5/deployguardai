from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


DataMode = Literal["synthetic", "connected"]
RiskLevel = Literal["low", "moderate", "high", "critical"]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class HealthResponse(APIModel):
    status: Literal["ok"]
    database: Literal["ready"]
    service: str
    data_mode: DataMode


class RiskDimension(APIModel):
    key: str
    label: str
    score: int = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    reason: str
    evidence_ids: list[str]


class RiskLedger(APIModel):
    overall_score: int = Field(ge=0, le=100)
    level: RiskLevel
    data_quality: float = Field(ge=0, le=1)
    dimensions: list[RiskDimension]
    recommendations: list[str]


class BlastNode(APIModel):
    id: str
    label: str
    kind: str
    team: str
    tier: str
    health: str
    impact_score: int = Field(ge=0, le=100)
    hop_distance: int = Field(ge=0)
    evidence_ids: list[str]


class BlastEdge(APIModel):
    source: str
    target: str
    relation: str
    confidence: float = Field(ge=0, le=1)
    active: bool


class BlastRadius(APIModel):
    nodes: list[BlastNode]
    edges: list[BlastEdge]


class ChangeDetail(APIModel):
    id: str
    workspace_id: str
    repository_id: str
    scenario_id: str
    data_mode: DataMode
    title: str
    repository: str
    author: str
    commit_sha: str
    branch: str
    created_at: datetime
    deployment_status: str
    deployment_environment: str
    changed_services: list[str]
    files_changed: int = Field(ge=0)
    lines_added: int = Field(ge=0)
    lines_deleted: int = Field(ge=0)
    flags: list[str]
    risk: RiskLedger
    blast_radius: BlastRadius


class TimelineEvent(APIModel):
    id: str
    timestamp: datetime
    type: str
    title: str
    detail: str
    service_id: str | None
    actor_user_id: str | None = None


class Evidence(APIModel):
    id: str
    type: str
    source: str
    timestamp: datetime
    summary: str
    value: str | int | float | bool | None
    quality: float = Field(ge=0, le=1)
    service_id: str | None
    supports: list[str]
    contradicts: list[str]


class Hypothesis(APIModel):
    id: str
    rank: int = Field(ge=1)
    cause_service: str
    cause: str
    confidence: float = Field(ge=0, le=1)
    score: int = Field(ge=0, le=100)
    evidence_ids: list[str]
    counter_evidence_ids: list[str]
    reasoning: str
    next_step: str
    status: str


class Feedback(APIModel):
    verdict: Literal["confirmed", "rejected", "partial"]
    hypothesis_id: str
    note: str
    submitted_at: datetime


class IncidentDetail(APIModel):
    id: str
    scenario_id: str
    data_mode: DataMode
    title: str
    severity: str
    status: str
    assignee_user_id: str | None = None
    started_at: datetime
    resolved_at: datetime | None
    affected_services: list[str]
    correlated_change_id: str | None
    summary: str
    timeline: list[TimelineEvent]
    evidence: list[Evidence]
    hypotheses: list[Hypothesis]
    feedback: list[Feedback]


class OverviewStats(APIModel):
    open_incidents: int = Field(ge=0)
    high_risk_changes: int = Field(ge=0)
    services_monitored: int = Field(ge=0)
    evidence_quality: float = Field(ge=0, le=1)


class Overview(APIModel):
    generated_at: datetime
    data_mode: DataMode
    active_scenario_id: str
    stats: OverviewStats
    active_change: ChangeDetail
    active_incident: IncidentDetail


class ScenarioSummary(APIModel):
    id: str
    name: str
    description: str
    repository: str
    data_mode: DataMode
    is_active: bool
    active_change_id: str
    active_incident_id: str


class AnalyzeChangeRequest(APIModel):
    title: NonEmptyString = Field(max_length=240)
    repository: NonEmptyString = Field(max_length=240)
    author: NonEmptyString = Field(max_length=160)
    commit_sha: str | None = Field(
        default=None,
        min_length=7,
        max_length=64,
        pattern=r"^[0-9a-fA-F]+$",
    )
    branch: str | None = Field(default=None, min_length=1, max_length=160)
    deployment_environment: str = Field(
        default="staging",
        min_length=1,
        max_length=80,
    )
    files_changed: int = Field(ge=0, le=100_000)
    lines_added: int = Field(ge=0, le=10_000_000)
    lines_deleted: int = Field(ge=0, le=10_000_000)
    changed_services: list[NonEmptyString] = Field(min_length=1, max_length=100)
    flags: list[NonEmptyString] = Field(default_factory=list, max_length=100)
    test_coverage: float = Field(ge=0, le=1)
    rollback_ready: bool
    observability_score: float = Field(ge=0, le=1)
    previous_failures: int = Field(ge=0, le=10_000)

    @field_validator("changed_services", "flags")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class FeedbackRequest(APIModel):
    hypothesis_id: NonEmptyString = Field(max_length=100)
    verdict: Literal["confirmed", "rejected", "partial"]
    note: NonEmptyString = Field(max_length=2_000)


class DoraMetricsResponse(APIModel):
    period: str
    deployment_frequency_per_week: float = Field(ge=0)
    change_lead_time_minutes: float = Field(ge=0)
    change_failure_rate: float = Field(ge=0, le=1)
    mean_time_to_restore_minutes: float = Field(ge=0)
    deployment_rework_rate: float = Field(ge=0, le=1)
    total_deployments: int = Field(ge=0)
    total_incidents: int = Field(ge=0)


class GitHubWebhookResponse(APIModel):
    status: Literal["accepted", "ignored"]
    event: str
    delivery_id: str
    change_id: str | None = None
    detail: str


class TelemetryIngestRequest(APIModel):
    source: NonEmptyString = Field(max_length=100)
    type: Literal["metric", "log", "trace", "alert"]
    service_id: NonEmptyString = Field(max_length=100)
    summary: NonEmptyString = Field(max_length=500)
    value: str | int | float | bool | None = None
    supports_hypothesis_ids: list[str] = Field(default_factory=list)
    contradicts_hypothesis_ids: list[str] = Field(default_factory=list)


class LLMSynthesisResponse(APIModel):
    incident_id: str
    model_used: str
    confidence: float = Field(ge=0, le=1)
    hypotheses: list[Hypothesis]
    unsupported_claims_count: int = Field(ge=0)
    citation_coverage: float = Field(ge=0, le=1)


WorkspaceRole = Literal["viewer", "responder", "admin", "owner"]


class UserSummary(APIModel):
    id: str
    email: str
    display_name: str
    auth_provider: str


class WorkspaceCreate(APIModel):
    name: NonEmptyString = Field(max_length=120)
    slug: NonEmptyString = Field(max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class WorkspaceSummary(APIModel):
    id: str
    name: str
    slug: str
    role: WorkspaceRole
    repository_count: int = Field(ge=0)
    member_count: int = Field(ge=0)
    created_at: datetime


class MembershipSummary(APIModel):
    user: UserSummary
    role: WorkspaceRole
    joined_at: datetime


class RepositoryCreate(APIModel):
    full_name: NonEmptyString = Field(max_length=240, pattern=r"^[^/\s]+/[^/\s]+$")
    default_branch: NonEmptyString = Field(default="main", max_length=160)
    visibility: Literal["private", "public", "internal"] = "private"


class RepositorySummary(APIModel):
    id: str
    workspace_id: str
    provider: Literal["development", "github"]
    provider_repository_id: str
    full_name: str
    default_branch: str
    visibility: str
    connection_state: str
    data_mode: DataMode
    selected: bool
    last_synced_at: datetime | None
    created_at: datetime


class InvitationCreate(APIModel):
    email: NonEmptyString = Field(max_length=320)
    role: Literal["viewer", "responder", "admin"] = "viewer"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        local, separator, domain = normalized.rpartition("@")
        if not separator or not local or "." not in domain:
            raise ValueError("Enter a valid email address")
        return normalized


class InvitationSummary(APIModel):
    id: str
    workspace_id: str
    email: str
    role: Literal["viewer", "responder", "admin"]
    status: Literal["pending", "accepted", "revoked", "expired"]
    created_at: datetime
    expires_at: datetime


class InvitationCreated(InvitationSummary):
    delivery_mode: Literal["smtp", "development_outbox", "disabled"]
    delivery_status: Literal[
        "sent", "failed", "development_outbox", "disabled"
    ]
    claim_token: str | None = None
    accept_path: str | None = None


class InvitationAccept(APIModel):
    token: NonEmptyString = Field(max_length=500)


class AuditEventSummary(APIModel):
    id: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str
    event_metadata: dict[str, object]
    created_at: datetime


class DevelopmentSessionRequest(APIModel):
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=160)


class SessionResponse(APIModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_at: datetime
    provider: Literal["development"]
    user: UserSummary
    workspaces: list[WorkspaceSummary]


class UserContextResponse(APIModel):
    workspace_id: str | None
    repository_id: str | None
    scenario_id: str | None


class UserContextUpdate(APIModel):
    workspace_id: NonEmptyString = Field(max_length=36)
    repository_id: str | None = Field(default=None, max_length=36)
    scenario_id: str | None = Field(default=None, max_length=80)
