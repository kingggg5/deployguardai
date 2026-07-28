import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import DomainError
from .github_client import GitHubAppClient
from .models import Repository, Scenario, User
from .provider_models import (
    ProviderAuthorizationState,
    ProviderConnection,
    WebhookDelivery,
)
from .provider_schemas import (
    GitHubConnectionSummary,
    GitHubInstallStart,
    GitHubRepositoryCandidate,
    GitHubRepositorySyncResponse,
    ProductCapabilities,
)
from .workspace_services import audit, membership_for, new_id, token_digest


def capabilities(settings) -> ProductCapabilities:
    return ProductCapabilities(
        environment=settings.environment,
        auth_provider=settings.auth_provider,
        development_identity=settings.development_auth_available(),
        github_app=settings.github_app_available(),
        email_delivery=settings.email_delivery_mode(),
        connected_telemetry=bool(settings.telemetry_ingest_token),
        oidc_authority=(
            settings.oidc_issuer if settings.auth_provider == "oidc" else None
        ),
        oidc_client_id=(
            settings.oidc_client_id if settings.auth_provider == "oidc" else None
        ),
        oidc_scope=(
            settings.oidc_scope if settings.auth_provider == "oidc" else None
        ),
    )


def github_client(settings) -> GitHubAppClient:
    if not settings.github_app_available():
        raise DomainError(
            "GitHub App is not configured", "github_app_not_configured", 503
        )
    return GitHubAppClient(
        app_id=settings.github_app_id,
        private_key=settings.github_app_private_key,
        api_url=settings.github_api_url,
        api_version=settings.github_api_version,
    )


def begin_github_installation(
    session: Session,
    user: User,
    workspace_id: str,
    request_id: str,
    settings,
) -> GitHubInstallStart:
    membership_for(session, user, workspace_id, "admin")
    if not settings.github_app_available():
        raise DomainError(
            "GitHub App is not configured", "github_app_not_configured", 503
        )
    raw_state = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    session.add(
        ProviderAuthorizationState(
            id=new_id(),
            state_hash=token_digest(raw_state),
            provider="github",
            workspace_id=workspace_id,
            user_id=user.id,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
            consumed_at=None,
        )
    )
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="provider.github.install_started",
        resource_type="provider_connection",
        resource_id="github",
        request_id=request_id,
    )
    session.commit()
    query = urlencode({"state": raw_state})
    return GitHubInstallStart(
        install_url=(
            f"https://github.com/apps/{settings.github_app_slug}"
            f"/installations/new?{query}"
        ),
        expires_at=expires_at,
    )


def complete_github_installation(
    session: Session,
    *,
    installation_id: str,
    raw_state: str,
    setup_action: str,
    request_id: str,
    settings,
) -> ProviderConnection:
    state = session.scalar(
        select(ProviderAuthorizationState).where(
            ProviderAuthorizationState.state_hash == token_digest(raw_state),
            ProviderAuthorizationState.provider == "github",
        )
    )
    if (
        state is None
        or state.consumed_at is not None
        or state.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC)
    ):
        raise DomainError(
            "GitHub installation state is invalid or expired",
            "invalid_provider_state",
            400,
        )
    if setup_action not in {"install", "update"}:
        raise DomainError(
            "GitHub installation was not completed",
            "github_installation_incomplete",
            400,
        )
    installation = github_client(settings).installation(installation_id)
    account = installation.get("account") or {}
    if not account.get("id") or not account.get("login"):
        raise DomainError(
            "GitHub installation account is incomplete",
            "github_installation_invalid",
            502,
        )
    existing_installation = session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.installation_id == installation_id
        )
    )
    if (
        existing_installation is not None
        and existing_installation.workspace_id != state.workspace_id
    ):
        raise DomainError(
            "GitHub installation is already linked to another workspace",
            "github_installation_already_linked",
            409,
        )
    connection = session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == state.workspace_id,
            ProviderConnection.provider == "github",
        )
    )
    timestamp = datetime.now(UTC)
    signed_installation_event = session.scalar(
        select(WebhookDelivery.id).where(
            WebhookDelivery.provider == "github",
            WebhookDelivery.installation_id == installation_id,
            WebhookDelivery.event_type.in_(
                ["installation", "installation_repositories"]
            ),
            WebhookDelivery.status.in_(["verified", "verified_unmapped"]),
        )
    )
    verified_state = (
        "connected" if signed_installation_event else "pending_verification"
    )
    if connection is None:
        connection = ProviderConnection(
            id=new_id(),
            workspace_id=state.workspace_id,
            provider="github",
            installation_id=installation_id,
            external_account_id=str(account["id"]),
            external_account_login=str(account["login"]),
            external_account_type=str(account.get("type", "Account")),
            connection_state=verified_state,
            permissions=installation.get("permissions") or {},
            repository_selection=str(
                installation.get("repository_selection", "selected")
            ),
            created_by_user_id=state.user_id,
            created_at=timestamp,
            updated_at=timestamp,
            last_synced_at=None,
            error_code=None,
        )
        session.add(connection)
    else:
        connection.installation_id = installation_id
        connection.external_account_id = str(account["id"])
        connection.external_account_login = str(account["login"])
        connection.external_account_type = str(account.get("type", "Account"))
        connection.connection_state = verified_state
        connection.permissions = installation.get("permissions") or {}
        connection.repository_selection = str(
            installation.get("repository_selection", "selected")
        )
        connection.updated_at = timestamp
        connection.error_code = None
    state.consumed_at = timestamp
    audit(
        session,
        workspace_id=state.workspace_id,
        actor_user_id=state.user_id,
        action=(
            "provider.github.connected"
            if verified_state == "connected"
            else "provider.github.pending_verification"
        ),
        resource_type="provider_connection",
        resource_id=connection.id,
        request_id=request_id,
        metadata={
            "account_login": connection.external_account_login,
            "installation_id": installation_id,
        },
    )
    session.commit()
    return connection


def connection_summary(connection: ProviderConnection) -> GitHubConnectionSummary:
    return GitHubConnectionSummary(
        id=connection.id,
        workspace_id=connection.workspace_id,
        installation_id=connection.installation_id,
        account_login=connection.external_account_login,
        account_type=connection.external_account_type,
        connection_state=connection.connection_state,
        permissions={
            str(key): str(value)
            for key, value in (connection.permissions or {}).items()
        },
        repository_selection=connection.repository_selection,
        last_synced_at=connection.last_synced_at,
        error_code=connection.error_code,
    )


def github_connection(
    session: Session, user: User, workspace_id: str
) -> ProviderConnection:
    membership_for(session, user, workspace_id)
    connection = session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == workspace_id,
            ProviderConnection.provider == "github",
        )
    )
    if connection is None:
        raise DomainError(
            "GitHub App is not connected", "github_connection_not_found", 404
        )
    return connection


def available_github_repositories(
    session: Session,
    user: User,
    workspace_id: str,
    settings,
) -> list[GitHubRepositoryCandidate]:
    connection = github_connection(session, user, workspace_id)
    if connection.connection_state != "connected":
        raise DomainError(
            "GitHub connection needs attention",
            "github_connection_unavailable",
            409,
        )
    records = github_client(settings).list_installation_repositories(
        connection.installation_id
    )
    selected_ids = set(
        session.scalars(
            select(Repository.provider_repository_id).where(
                Repository.workspace_id == workspace_id,
                Repository.provider == "github",
                Repository.selected.is_(True),
            )
        ).all()
    )
    return [
        GitHubRepositoryCandidate(
            provider_repository_id=str(item["id"]),
            full_name=str(item["full_name"]),
            default_branch=str(item.get("default_branch") or "main"),
            visibility=_visibility(item),
            html_url=str(item.get("html_url") or ""),
            archived=bool(item.get("archived", False)),
            selected=str(item["id"]) in selected_ids,
            pushed_at=item.get("pushed_at"),
        )
        for item in records
        if item.get("id") and item.get("full_name")
    ]


def sync_github_repositories(
    session: Session,
    user: User,
    workspace_id: str,
    repository_ids: list[str],
    request_id: str,
    settings,
) -> GitHubRepositorySyncResponse:
    membership_for(session, user, workspace_id, "admin")
    connection = github_connection(session, user, workspace_id)
    available = github_client(settings).list_installation_repositories(
        connection.installation_id
    )
    by_id = {str(item["id"]): item for item in available if item.get("id")}
    requested = set(repository_ids)
    missing = requested - set(by_id)
    if missing:
        raise DomainError(
            "One or more repositories are not accessible to this installation",
            "github_repository_not_accessible",
            400,
        )
    existing = session.scalars(
        select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.provider == "github",
        )
    ).all()
    existing_by_provider_id = {
        repository.provider_repository_id: repository for repository in existing
    }
    timestamp = datetime.now(UTC)
    imported = 0
    for provider_id in requested:
        source = by_id[provider_id]
        repository = existing_by_provider_id.get(provider_id)
        if repository is None:
            repository = Repository(
                id=new_id(),
                workspace_id=workspace_id,
                provider="github",
                provider_repository_id=provider_id,
                full_name=str(source["full_name"]),
                default_branch=str(source.get("default_branch") or "main"),
                visibility=_visibility(source),
                connection_state="connected",
                data_mode="connected",
                selected=True,
                last_synced_at=timestamp,
                created_at=timestamp,
            )
            session.add(repository)
            session.flush()
            imported += 1
        else:
            repository.full_name = str(source["full_name"])
            repository.default_branch = str(
                source.get("default_branch") or "main"
            )
            repository.visibility = _visibility(source)
            repository.connection_state = "connected"
            repository.data_mode = "connected"
            repository.selected = True
            repository.last_synced_at = timestamp
        _ensure_connected_scenario(session, repository, timestamp)
    deselected = 0
    for repository in existing:
        if repository.provider_repository_id not in requested and repository.selected:
            repository.selected = False
            deselected += 1
    connection.last_synced_at = timestamp
    connection.updated_at = timestamp
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="provider.github.repositories_synced",
        resource_type="provider_connection",
        resource_id=connection.id,
        request_id=request_id,
        metadata={"selected_count": len(requested)},
    )
    session.commit()
    return GitHubRepositorySyncResponse(
        imported=imported,
        deselected=deselected,
        synced_at=timestamp,
    )


def disconnect_github(
    session: Session,
    user: User,
    workspace_id: str,
    request_id: str,
) -> GitHubConnectionSummary:
    membership_for(session, user, workspace_id, "admin")
    connection = github_connection(session, user, workspace_id)
    connection.connection_state = "revoked"
    connection.updated_at = datetime.now(UTC)
    repositories = session.scalars(
        select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.provider == "github",
        )
    ).all()
    for repository in repositories:
        repository.connection_state = "revoked"
        repository.selected = False
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="provider.github.disconnected",
        resource_type="provider_connection",
        resource_id=connection.id,
        request_id=request_id,
    )
    session.commit()
    return connection_summary(connection)


def _visibility(repository: dict) -> str:
    value = str(repository.get("visibility") or "").lower()
    if value in {"public", "private", "internal"}:
        return value
    return "private" if repository.get("private") else "public"


def _ensure_connected_scenario(
    session: Session, repository: Repository, timestamp: datetime
) -> None:
    scenario = session.scalar(
        select(Scenario).where(
            Scenario.workspace_id == repository.workspace_id,
            Scenario.repository_id == repository.id,
            Scenario.data_mode == "connected",
        )
    )
    if scenario is not None:
        return
    session.add(
        Scenario(
            id=f"github-{repository.id}",
            workspace_id=repository.workspace_id,
            repository_id=repository.id,
            name=repository.full_name,
            description=(
                "Connected GitHub evidence context. The dependency graph remains "
                "empty until topology evidence is ingested."
            ),
            data_mode="connected",
            is_active=True,
            sort_order=1,
            active_change_id=None,
            active_incident_id=None,
            service_graph={"nodes": [], "edges": [], "updated_at": timestamp.isoformat()},
        )
    )
