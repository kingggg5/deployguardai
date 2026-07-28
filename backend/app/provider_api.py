from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from .errors import DomainError
from .models import Repository, User
from .schemas import ChangeDetail
from .services import list_changes
from .workspace_services import membership_for
from .provider_schemas import (
    GitHubConnectionSummary,
    GitHubInstallStart,
    GitHubRepositoryCandidate,
    GitHubRepositorySyncRequest,
    GitHubRepositorySyncResponse,
    ProductCapabilities,
)
from .provider_services import (
    available_github_repositories,
    begin_github_installation,
    capabilities,
    complete_github_installation,
    connection_summary,
    disconnect_github,
    github_connection,
    sync_github_repositories,
)
from .workspace_api import get_current_user, get_session, request_id


router = APIRouter(prefix="/api/v1")


@router.get("/capabilities", response_model=ProductCapabilities)
def product_capabilities(request: Request) -> ProductCapabilities:
    return capabilities(request.app.state.settings)


@router.get(
    "/workspaces/{workspace_id}/repositories/{repository_id}/changes",
    response_model=list[ChangeDetail],
)
def connected_repository_changes(
    workspace_id: str,
    repository_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[ChangeDetail]:
    membership_for(session, user, workspace_id)
    repository = session.scalar(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.workspace_id == workspace_id,
            Repository.data_mode == "connected",
        )
    )
    if repository is None:
        raise DomainError("Repository not found", "repository_not_found", 404)
    return list_changes(session, workspace_id, repository_id)


@router.post(
    "/workspaces/{workspace_id}/providers/github/install",
    response_model=GitHubInstallStart,
)
def github_install(
    workspace_id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> GitHubInstallStart:
    return begin_github_installation(
        session,
        user,
        workspace_id,
        request_id(request),
        request.app.state.settings,
    )


@router.get("/providers/github/callback", include_in_schema=False)
def github_callback(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    installation_id: Annotated[str, Query(min_length=1, max_length=80)],
    setup_action: Annotated[str, Query(min_length=1, max_length=20)],
    state: Annotated[str, Query(min_length=20, max_length=500)],
) -> RedirectResponse:
    settings = request.app.state.settings
    connection = complete_github_installation(
        session,
        installation_id=installation_id,
        raw_state=state,
        setup_action=setup_action,
        request_id=request_id(request),
        settings=settings,
    )
    query = urlencode(
        {
            "view": "workspace",
            "github": "connected",
            "workspace": connection.workspace_id,
        }
    )
    return RedirectResponse(
        f"{settings.frontend_public_url.rstrip('/')}/?{query}", status_code=303
    )


@router.get(
    "/workspaces/{workspace_id}/providers/github",
    response_model=GitHubConnectionSummary,
)
def github_status(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> GitHubConnectionSummary:
    return connection_summary(github_connection(session, user, workspace_id))


@router.get(
    "/workspaces/{workspace_id}/providers/github/repositories",
    response_model=list[GitHubRepositoryCandidate],
)
def github_repositories(
    workspace_id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[GitHubRepositoryCandidate]:
    return available_github_repositories(
        session, user, workspace_id, request.app.state.settings
    )


@router.post(
    "/workspaces/{workspace_id}/providers/github/repositories/sync",
    response_model=GitHubRepositorySyncResponse,
)
def github_repositories_sync(
    workspace_id: str,
    payload: GitHubRepositorySyncRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> GitHubRepositorySyncResponse:
    return sync_github_repositories(
        session,
        user,
        workspace_id,
        payload.repository_ids,
        request_id(request),
        request.app.state.settings,
    )


@router.delete(
    "/workspaces/{workspace_id}/providers/github",
    response_model=GitHubConnectionSummary,
)
def github_disconnect(
    workspace_id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> GitHubConnectionSummary:
    return disconnect_github(
        session, user, workspace_id, request_id(request)
    )
