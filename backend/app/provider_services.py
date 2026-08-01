import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .errors import DomainError
from .github_client import GitHubAppClient
from .models import ChangeRecord, Repository, Scenario, User
from .operations_models import WorkspaceRiskPolicy
from .provider_models import (
    GitHubCheckPublication,
    ProviderAuthorizationState,
    ProviderConnection,
    WebhookDelivery,
)
from .provider_schemas import (
    ConnectorHealthSummary,
    GitHubConnectionSummary,
    GitHubCheckRunResponse,
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
        github_checks=(
            settings.github_app_available() and settings.github_checks_enabled
        ),
        email_delivery=settings.email_delivery_mode(),
        connected_telemetry=bool(settings.telemetry_ingest_token),
        telemetry_scope=(
            "workspace_credential"
            if settings.telemetry_ingest_token
            else "disabled"
        ),
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


def connector_health(
    session: Session,
    user: User,
    workspace_id: str,
) -> list[ConnectorHealthSummary]:
    membership_for(session, user, workspace_id)
    connections = session.scalars(
        select(ProviderConnection)
        .where(ProviderConnection.workspace_id == workspace_id)
        .order_by(ProviderConnection.provider, ProviderConnection.id)
    ).all()
    result: list[ConnectorHealthSummary] = []
    stale_cutoff = datetime.now(UTC) - timedelta(minutes=5)
    successful_delivery_states = ("processed", "verified", "ignored")
    for connection in connections:
        latest_delivery = session.scalar(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.workspace_id == workspace_id,
                WebhookDelivery.provider == connection.provider,
            )
            .order_by(
                WebhookDelivery.created_at.desc(),
                WebhookDelivery.id.desc(),
            )
        )
        last_success_at = session.scalar(
            select(func.max(WebhookDelivery.created_at)).where(
                WebhookDelivery.workspace_id == workspace_id,
                WebhookDelivery.provider == connection.provider,
                WebhookDelivery.status.in_(successful_delivery_states),
            )
        )
        last_failure_at = session.scalar(
            select(func.max(WebhookDelivery.created_at)).where(
                WebhookDelivery.workspace_id == workspace_id,
                WebhookDelivery.provider == connection.provider,
                WebhookDelivery.status == "failed",
            )
        )
        stuck_delivery_count = int(
            session.scalar(
                select(func.count(WebhookDelivery.id)).where(
                    WebhookDelivery.workspace_id == workspace_id,
                    WebhookDelivery.provider == connection.provider,
                    WebhookDelivery.status == "processing",
                    WebhookDelivery.created_at < stale_cutoff,
                )
            )
            or 0
        )
        selected_resource_count = int(
            session.scalar(
                select(func.count(Repository.id)).where(
                    Repository.workspace_id == workspace_id,
                    Repository.provider == connection.provider,
                    Repository.selected.is_(True),
                    Repository.connection_state == "connected",
                )
            )
            or 0
        )
        retrying_publication_count = 0
        permanent_failure_count = 0
        if connection.provider == "github":
            retrying_publication_count = int(
                session.scalar(
                    select(func.count(GitHubCheckPublication.id)).where(
                        GitHubCheckPublication.workspace_id == workspace_id,
                        GitHubCheckPublication.status == "retryable_failed",
                    )
                )
                or 0
            )
            permanent_failure_count = int(
                session.scalar(
                    select(func.count(GitHubCheckPublication.id)).where(
                        GitHubCheckPublication.workspace_id == workspace_id,
                        GitHubCheckPublication.status == "permanent_failed",
                    )
                )
                or 0
            )

        reasons: list[str] = []
        state = connection.connection_state
        if state == "pending_verification":
            health_status = "pending"
            reasons.append("provider_verification_pending")
        elif state == "revoked":
            health_status = "revoked"
            reasons.append("provider_access_revoked")
        else:
            if state != "connected":
                reasons.append("provider_connection_unavailable")
            if connection.error_code:
                reasons.append("provider_error_recorded")
            if (
                last_failure_at is not None
                and (
                    last_success_at is None
                    or last_failure_at > last_success_at
                )
            ):
                reasons.append("latest_delivery_failed")
            if stuck_delivery_count:
                reasons.append("stuck_webhook_delivery")
            if permanent_failure_count:
                reasons.append("permanent_publication_failure")
            health_status = "degraded" if reasons else "healthy"

        result.append(
            ConnectorHealthSummary(
                connection_id=connection.id,
                workspace_id=workspace_id,
                provider=connection.provider,
                status=health_status,
                connection_state=state,
                selected_resource_count=selected_resource_count,
                last_synced_at=connection.last_synced_at,
                last_delivery_at=(
                    latest_delivery.created_at
                    if latest_delivery is not None
                    else None
                ),
                last_delivery_status=(
                    latest_delivery.status
                    if latest_delivery is not None
                    else None
                ),
                last_success_at=last_success_at,
                last_failure_at=last_failure_at,
                stuck_delivery_count=stuck_delivery_count,
                retrying_publication_count=retrying_publication_count,
                permanent_failure_count=permanent_failure_count,
                error_code=connection.error_code,
                reasons=reasons,
            )
        )
    return result


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


GITHUB_CHECK_RETRYABLE_ERRORS = {
    "github_api_error",
    "github_api_invalid_response",
    "github_api_unavailable",
    "github_check_publish_failed",
    "github_rate_limited",
    "github_token_exchange_failed",
}


def _github_check_publication(
    session: Session,
    *,
    connection: ProviderConnection,
    repository: Repository,
    change: ChangeRecord,
    conclusion: str,
    details_url: str,
) -> GitHubCheckPublication:
    publication = session.scalar(
        select(GitHubCheckPublication)
        .where(
            GitHubCheckPublication.repository_id == repository.id,
            GitHubCheckPublication.head_sha == change.commit_sha,
        )
        .with_for_update()
    )
    timestamp = datetime.now(UTC)
    if publication is None:
        publication_id = new_id()
        publication = GitHubCheckPublication(
            id=publication_id,
            workspace_id=connection.workspace_id,
            repository_id=repository.id,
            change_id=change.id,
            head_sha=change.commit_sha,
            external_id=publication_id,
            provider_check_id=None,
            status="pending",
            conclusion=conclusion,
            details_url=details_url,
            attempt_count=0,
            last_error_code=None,
            next_retry_at=None,
            created_at=timestamp,
            updated_at=timestamp,
            published_at=None,
        )
        session.add(publication)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            publication = session.scalar(
                select(GitHubCheckPublication).where(
                    GitHubCheckPublication.repository_id == repository.id,
                    GitHubCheckPublication.head_sha == change.commit_sha,
                )
            )
            if publication is None:
                raise
    publication.change_id = change.id
    publication.conclusion = conclusion
    publication.details_url = details_url
    publication.updated_at = timestamp
    session.commit()
    return publication


def _github_check_retry_delay(attempt_count: int) -> timedelta:
    seconds = min(3_600, 30 * (2 ** min(max(attempt_count - 1, 0), 7)))
    return timedelta(seconds=seconds)


def _publish_github_change_check(
    session: Session,
    *,
    connection: ProviderConnection,
    repository: Repository,
    change: ChangeRecord,
    actor_user_id: str | None,
    request_id: str,
    settings,
) -> GitHubCheckRunResponse:
    score = int((change.risk or {}).get("overall_score", 0))
    level = str((change.risk or {}).get("level", "unknown"))
    quality = float((change.risk or {}).get("data_quality", 0.0))
    recommendations = [
        str(item)
        for item in (change.risk or {}).get("recommendations", [])
    ]
    policy = session.get(WorkspaceRiskPolicy, connection.workspace_id)
    policy_enabled = policy.enabled if policy is not None else True
    warn_threshold = policy.warn_threshold if policy is not None else 60
    block_threshold = policy.block_threshold if policy is not None else 80
    policy_version = policy.version if policy is not None else 1
    require_tests = policy.require_tests if policy is not None else True
    require_rollback = policy.require_rollback if policy is not None else True
    max_blast_radius = policy.max_blast_radius if policy is not None else 10
    policy_findings: list[str] = []
    if policy_enabled:
        if score >= block_threshold:
            policy_findings.append(
                f"Risk score meets the escalation threshold ({block_threshold})."
            )
        elif score >= warn_threshold:
            policy_findings.append(
                f"Risk score meets the review threshold ({warn_threshold})."
            )
        if require_tests and change.test_coverage <= 0:
            policy_findings.append("Required test coverage evidence is missing.")
        if require_rollback and not change.rollback_ready:
            policy_findings.append("Required rollback readiness is missing.")
        impacted_services = len(
            [
                item
                for item in (change.blast_radius or {}).get("nodes", [])
                if int(item.get("impact_score", 0)) > 0
            ]
        )
        if (
            impacted_services > max_blast_radius
        ):
            policy_findings.append(
                "Blast radius exceeds the workspace maximum "
                f"({impacted_services}/{max_blast_radius} services)."
            )
    conclusion = "neutral" if policy_findings else "success"
    if score >= block_threshold and policy_enabled:
        title = f"Escalated review · risk {score}/100"
    elif conclusion == "neutral":
        title = f"Review recommended · risk {score}/100"
    else:
        title = f"Normal review · risk {score}/100"
    summary_lines = [
        f"Deterministic change risk: **{score}/100 ({level})**.",
        f"Evidence quality: **{quality:.0%}**.",
        (
            f"Workspace policy: **v{policy_version} "
            f"({'enabled' if policy_enabled else 'disabled'})**."
        ),
        *(
            ["", "### Policy findings", *[f"- {item}" for item in policy_findings]]
            if policy_findings
            else []
        ),
        "",
        "### Verify next",
        *(
            [f"- {item}" for item in recommendations]
            or ["- Continue with the normal review path."]
        ),
        "",
        (
            "DeployGuard provides decision support only. This check does not "
            "deploy, roll back, or remediate infrastructure."
        ),
    ]
    details_url = (
        f"{settings.frontend_public_url.rstrip('/')}/?"
        + urlencode(
            {
                "view": "change_risk",
                "workspace": connection.workspace_id,
                "repository": repository.id,
                "scenario": change.scenario_id,
                "change": change.id,
            }
        )
    )
    publication = _github_check_publication(
        session,
        connection=connection,
        repository=repository,
        change=change,
        conclusion=conclusion,
        details_url=details_url,
    )
    previous_attempts = publication.attempt_count
    publication.status = "publishing"
    publication.attempt_count += 1
    publication.last_error_code = None
    publication.next_retry_at = None
    publication.updated_at = datetime.now(UTC)
    session.commit()

    client = github_client(settings)
    try:
        provider_check_id = publication.provider_check_id
        if provider_check_id is None and previous_attempts > 0:
            recovered = client.find_check_run(
                installation_id=connection.installation_id,
                repository_full_name=repository.full_name,
                head_sha=change.commit_sha,
                external_id=publication.external_id,
            )
            if recovered is not None:
                provider_check_id = str(recovered.get("id") or "")
        request_payload = {
            "installation_id": connection.installation_id,
            "repository_full_name": repository.full_name,
            "head_sha": change.commit_sha,
            "external_id": publication.external_id,
            "conclusion": conclusion,
            "title": title,
            "summary": "\n".join(summary_lines),
            "details_url": details_url,
        }
        if provider_check_id:
            result = client.update_check_run(
                provider_check_id=provider_check_id,
                **request_payload,
            )
        else:
            result = client.create_check_run(**request_payload)
        provider_check_id = str(result.get("id") or provider_check_id or "")
        if not provider_check_id:
            raise DomainError(
                "GitHub did not return a Check Run ID",
                "github_check_publish_failed",
                502,
            )
    except DomainError as error:
        session.rollback()
        failed = session.get(GitHubCheckPublication, publication.id)
        if failed is not None:
            retryable = error.code in GITHUB_CHECK_RETRYABLE_ERRORS
            failed.status = (
                "retryable_failed" if retryable else "permanent_failed"
            )
            failed.last_error_code = error.code
            failed.next_retry_at = (
                datetime.now(UTC)
                + _github_check_retry_delay(failed.attempt_count)
                if retryable
                else None
            )
            failed.updated_at = datetime.now(UTC)
        persisted_connection = session.get(
            ProviderConnection, connection.id
        )
        if persisted_connection is not None:
            persisted_connection.error_code = error.code
            persisted_connection.updated_at = datetime.now(UTC)
            audit(
                session,
                workspace_id=persisted_connection.workspace_id,
                actor_user_id=actor_user_id,
                action="provider.github.check_publish_failed",
                resource_type="change",
                resource_id=change.id,
                request_id=request_id,
                metadata={
                    "error_code": error.code,
                    "retryable": error.code
                    in GITHUB_CHECK_RETRYABLE_ERRORS,
                    "publication_id": publication.id,
                },
            )
        session.commit()
        raise

    published_at = datetime.now(UTC)
    persisted_publication = session.get(
        GitHubCheckPublication, publication.id
    )
    if persisted_publication is None:
        raise DomainError(
            "GitHub Check publication state was lost",
            "github_check_publication_missing",
            500,
        )
    persisted_publication.provider_check_id = provider_check_id
    persisted_publication.status = "published"
    persisted_publication.conclusion = conclusion
    persisted_publication.details_url = details_url
    persisted_publication.last_error_code = None
    persisted_publication.next_retry_at = None
    persisted_publication.updated_at = published_at
    persisted_publication.published_at = published_at
    persisted_connection = session.get(ProviderConnection, connection.id)
    if persisted_connection is not None:
        persisted_connection.error_code = None
        persisted_connection.updated_at = published_at
    audit(
        session,
        workspace_id=publication.workspace_id,
        actor_user_id=actor_user_id,
        action="provider.github.check_published",
        resource_type="change",
        resource_id=change.id,
        request_id=request_id,
        metadata={
            "provider_check_id": provider_check_id,
            "publication_id": publication.id,
            "conclusion": conclusion,
            "risk_score": score,
            "attempt_count": persisted_publication.attempt_count,
        },
    )
    session.commit()
    return GitHubCheckRunResponse(
        provider_check_id=provider_check_id,
        change_id=change.id,
        status=str(result.get("status") or "completed"),
        conclusion=conclusion,
        details_url=details_url,
        published_at=published_at,
    )


def publish_github_change_check(
    session: Session,
    user: User,
    *,
    workspace_id: str,
    repository_id: str,
    change_id: str,
    request_id: str,
    settings,
) -> GitHubCheckRunResponse:
    membership_for(session, user, workspace_id, "responder")
    if not settings.github_checks_enabled:
        raise DomainError(
            "GitHub Check publishing is disabled",
            "github_checks_disabled",
            409,
        )
    connection = github_connection(session, user, workspace_id)
    if connection.connection_state != "connected":
        raise DomainError(
            "GitHub connection needs attention",
            "github_connection_unavailable",
            409,
        )
    if str((connection.permissions or {}).get("checks", "")).lower() != "write":
        raise DomainError(
            "The GitHub App needs Checks: write permission",
            "github_checks_permission_missing",
            409,
        )
    repository = session.scalar(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.workspace_id == workspace_id,
            Repository.provider == "github",
            Repository.selected.is_(True),
        )
    )
    if repository is None:
        raise DomainError("Repository not found", "repository_not_found", 404)
    change = session.scalar(
        select(ChangeRecord).where(
            ChangeRecord.id == change_id,
            ChangeRecord.workspace_id == workspace_id,
            ChangeRecord.repository_id == repository_id,
            ChangeRecord.data_mode == "connected",
        )
    )
    if change is None:
        raise DomainError("Change not found", "change_not_found", 404)
    return _publish_github_change_check(
        session,
        connection=connection,
        repository=repository,
        change=change,
        actor_user_id=user.id,
        request_id=request_id,
        settings=settings,
    )


def publish_github_change_check_from_webhook(
    session: Session,
    *,
    connection: ProviderConnection,
    repository: Repository,
    change: ChangeRecord,
    request_id: str,
    settings,
) -> GitHubCheckRunResponse | None:
    if (
        not settings.github_checks_enabled
        or connection.connection_state != "connected"
        or str((connection.permissions or {}).get("checks", "")).lower()
        != "write"
    ):
        return None
    try:
        return _publish_github_change_check(
            session,
            connection=connection,
            repository=repository,
            change=change,
            actor_user_id=None,
            request_id=request_id,
            settings=settings,
        )
    except DomainError as error:
        if error.code in GITHUB_CHECK_RETRYABLE_ERRORS:
            raise
        return None


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
