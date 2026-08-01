from datetime import datetime
from typing import Literal

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
    provider_url: str | None
    service_ids: list[str]
    last_event_id: str | None
    provider_created_at: datetime
    provider_updated_at: datetime
    finished_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
