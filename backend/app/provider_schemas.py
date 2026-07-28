from datetime import datetime
from typing import Literal

from pydantic import Field

from .schemas import APIModel


class ProductCapabilities(APIModel):
    environment: str
    auth_provider: Literal["development", "oidc", "disabled"]
    development_identity: bool
    github_app: bool
    email_delivery: Literal["smtp", "development_outbox", "disabled"]
    connected_telemetry: bool
    oidc_authority: str | None = None
    oidc_client_id: str | None = None
    oidc_scope: str | None = None


class GitHubInstallStart(APIModel):
    install_url: str
    expires_at: datetime


class GitHubConnectionSummary(APIModel):
    id: str
    workspace_id: str
    installation_id: str
    account_login: str
    account_type: str
    connection_state: str
    permissions: dict[str, str]
    repository_selection: str
    last_synced_at: datetime | None
    error_code: str | None


class GitHubRepositoryCandidate(APIModel):
    provider_repository_id: str
    full_name: str
    default_branch: str
    visibility: Literal["private", "public", "internal"]
    html_url: str
    archived: bool
    selected: bool
    pushed_at: datetime | None


class GitHubRepositorySyncRequest(APIModel):
    repository_ids: list[str] = Field(min_length=1, max_length=500)


class GitHubRepositorySyncResponse(APIModel):
    imported: int = Field(ge=0)
    deselected: int = Field(ge=0)
    synced_at: datetime


class InvitationDeliverySummary(APIModel):
    provider: str
    status: Literal["queued", "sent", "failed", "development_outbox"]
    provider_message_id: str | None
    error_code: str | None
    attempted_at: datetime
