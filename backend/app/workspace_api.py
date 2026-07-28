from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from .auth.dependencies import get_current_user, get_session
from .errors import DomainError
from .email_delivery import deliver_invitation
from .models import User
from .schemas import (
    AuditEventSummary,
    DevelopmentSessionRequest,
    InvitationAccept,
    InvitationCreate,
    InvitationCreated,
    InvitationSummary,
    MembershipSummary,
    RepositoryCreate,
    RepositorySummary,
    SessionResponse,
    UserContextResponse,
    UserContextUpdate,
    UserSummary,
    WorkspaceCreate,
    WorkspaceSummary,
)
from .tenant import get_user_context, select_user_context
from .workspace_services import (
    accept_invitation,
    create_development_session,
    create_invitation,
    create_repository,
    create_workspace,
    list_audit_events,
    list_invitations,
    list_members,
    list_repositories,
    list_user_workspaces,
    revoke_invitation,
    user_summary,
)


router = APIRouter(prefix="/api/v1")


def request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    return supplied[:80] if supplied else str(uuid4())


@router.post(
    "/auth/development-session",
    response_model=SessionResponse,
)
def development_session(
    payload: DevelopmentSessionRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> SessionResponse:
    settings = request.app.state.settings
    if not settings.development_auth_available():
        raise DomainError(
            "Development identity provider is disabled",
            "development_auth_disabled",
            404,
        )
    email = (payload.email or settings.development_user_email).strip().lower()
    display_name = (
        payload.display_name
        or (settings.development_user_name if payload.email is None else email.split("@")[0])
    )
    response.headers["Cache-Control"] = "no-store"
    return create_development_session(
        session,
        email=email,
        display_name=display_name,
        token_ttl_hours=settings.access_token_ttl_hours,
    )


@router.get("/auth/me", response_model=UserSummary)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserSummary:
    return user_summary(user)


@router.get("/me/context", response_model=UserContextResponse)
def current_context(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UserContextResponse:
    return get_user_context(session, user)


@router.put("/me/context", response_model=UserContextResponse)
def context_select(
    payload: UserContextUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UserContextResponse:
    return select_user_context(session, user, payload)


@router.get("/workspaces", response_model=list[WorkspaceSummary])
def workspaces(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[WorkspaceSummary]:
    return list_user_workspaces(session, user)


@router.post(
    "/workspaces",
    response_model=WorkspaceSummary,
    status_code=status.HTTP_201_CREATED,
)
def workspace_create(
    payload: WorkspaceCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> WorkspaceSummary:
    return create_workspace(session, user, payload, request_id(request))


@router.get(
    "/workspaces/{workspace_id}/repositories",
    response_model=list[RepositorySummary],
)
def repositories(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[RepositorySummary]:
    return list_repositories(session, user, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/repositories",
    response_model=RepositorySummary,
    status_code=status.HTTP_201_CREATED,
)
def repository_create(
    workspace_id: str,
    payload: RepositoryCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> RepositorySummary:
    return create_repository(
        session, user, workspace_id, payload, request_id(request)
    )


@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=list[MembershipSummary],
)
def members(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[MembershipSummary]:
    return list_members(session, user, workspace_id)


@router.get(
    "/workspaces/{workspace_id}/invitations",
    response_model=list[InvitationSummary],
)
def invitations(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[InvitationSummary]:
    return list_invitations(session, user, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/invitations",
    response_model=InvitationCreated,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def invitation_create(
    workspace_id: str,
    payload: InvitationCreate,
    request: Request,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> InvitationCreated:
    if request.app.state.settings.email_delivery_mode() == "disabled":
        raise DomainError(
            "Invitation delivery is not configured",
            "invitation_delivery_not_configured",
            503,
        )
    response.headers["Cache-Control"] = "no-store"
    invitation = create_invitation(
        session,
        user,
        workspace_id,
        payload,
        request_id(request),
        request.app.state.settings.invitation_ttl_hours,
    )
    return deliver_invitation(session, invitation, request.app.state.settings)


@router.delete(
    "/workspaces/{workspace_id}/invitations/{invitation_id}",
    response_model=InvitationSummary,
)
def invitation_revoke(
    workspace_id: str,
    invitation_id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> InvitationSummary:
    return revoke_invitation(
        session,
        user,
        workspace_id,
        invitation_id,
        request_id(request),
    )


@router.post("/invitations/accept", response_model=WorkspaceSummary)
def invitation_accept(
    payload: InvitationAccept,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> WorkspaceSummary:
    return accept_invitation(
        session, user, payload.token, request_id(request)
    )


@router.get(
    "/workspaces/{workspace_id}/audit-events",
    response_model=list[AuditEventSummary],
)
def audit_events(
    workspace_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AuditEventSummary]:
    return list_audit_events(session, user, workspace_id, limit)
