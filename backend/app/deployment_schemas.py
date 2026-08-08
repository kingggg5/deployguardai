from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from pydantic import ConfigDict

from .schemas import APIModel


DeploymentStatus = Literal[
    "queued",
    "in_progress",
    "succeeded",
    "failed",
    "cancelled",
    "inactive",
    "unknown",
]

DeploymentOutcomeState = Literal[
    "unknown",
    "stable_window_met",
    "failed",
    "rolled_back",
    "incident_linked",
]


class DeploymentOutcomeRequest(APIModel):
    state: DeploymentOutcomeState
    summary: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    incident_id: str | None = Field(default=None, max_length=80)
    stable_window_minutes: int | None = Field(default=None, ge=1, le=43_200)

    @model_validator(mode="after")
    def state_requirements(self) -> "DeploymentOutcomeRequest":
        if self.state == "incident_linked" and not self.incident_id:
            raise ValueError("incident_id is required for incident_linked")
        if self.state == "stable_window_met" and self.stable_window_minutes is None:
            raise ValueError(
                "stable_window_minutes is required for stable_window_met"
            )
        return self


class DeploymentResponse(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    workspace_id: str
    repository_id: str
    change_id: str | None
    provider: str
    provider_deployment_id: str
    environment: str
    commit_sha: str | None
    ref: str | None
    status: DeploymentStatus
    outcome_state: Literal[
        "unknown",
        "stable_window_met",
        "failed",
        "rolled_back",
        "incident_linked",
    ]
    outcome_evidence: dict[str, object]
    outcome_incident_id: str | None
    outcome_confirmed_by_user_id: str | None
    outcome_confirmed_at: datetime | None
    provider_url: str | None
    service_ids: list[str]
    last_event_id: str | None
    provider_created_at: datetime
    provider_updated_at: datetime
    finished_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
