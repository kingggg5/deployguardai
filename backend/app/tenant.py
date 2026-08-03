from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth.dependencies import get_legacy_user, get_session
from .errors import DomainError
from .models import (
    LEGACY_REPOSITORY_ID,
    LEGACY_WORKSPACE_ID,
    Repository,
    Scenario,
    User,
    UserContext,
    Workspace,
    WorkspaceMembership,
)
from .schemas import UserContextResponse, UserContextUpdate
from .rls import set_tenant_context
from .workspace_services import ROLE_LEVEL, now_utc


@dataclass(frozen=True)
class TenantScope:
    user: User
    workspace_id: str
    repository_id: str | None
    scenario_id: str | None
    role: str


def _context_response(
    context: UserContext | None,
) -> UserContextResponse:
    if context is None:
        return UserContextResponse(
            workspace_id=None,
            repository_id=None,
            scenario_id=None,
        )
    return UserContextResponse.model_validate(context)


def get_user_context(
    session: Session, user: User
) -> UserContextResponse:
    return _context_response(session.get(UserContext, user.id))


def _default_repository(
    session: Session, workspace_id: str
) -> Repository | None:
    return session.scalar(
        select(Repository)
        .where(Repository.workspace_id == workspace_id)
        .order_by(Repository.selected.desc(), Repository.created_at, Repository.id)
    )


def _default_scenario(
    session: Session,
    workspace_id: str,
    repository_id: str | None,
) -> Scenario | None:
    statement = select(Scenario).where(Scenario.workspace_id == workspace_id)
    if repository_id is not None:
        statement = statement.where(Scenario.repository_id == repository_id)
    return session.scalar(
        statement.order_by(
            Scenario.is_active.desc(), Scenario.sort_order, Scenario.id
        )
    )


def ensure_context(
    session: Session,
    user: User,
    *,
    allow_legacy_bootstrap: bool = False,
) -> UserContext:
    context = session.get(UserContext, user.id)
    if context is not None:
        return context

    membership = session.scalar(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(WorkspaceMembership.joined_at, WorkspaceMembership.id)
    )
    if membership is None and allow_legacy_bootstrap:
        workspace = session.get(Workspace, LEGACY_WORKSPACE_ID)
        if workspace is not None:
            membership = WorkspaceMembership(
                id=str(uuid4()),
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
                joined_at=now_utc(),
            )
            session.add(membership)
            session.flush()
    if membership is None:
        raise DomainError(
            "Select or create a workspace first",
            "workspace_context_required",
            409,
        )

    set_tenant_context(session, membership.workspace_id)
    repository = _default_repository(session, membership.workspace_id)
    scenario = _default_scenario(
        session,
        membership.workspace_id,
        repository.id if repository is not None else None,
    )
    context = UserContext(
        user_id=user.id,
        workspace_id=membership.workspace_id,
        repository_id=repository.id if repository is not None else None,
        scenario_id=scenario.id if scenario is not None else None,
        updated_at=now_utc(),
    )
    session.add(context)
    session.commit()
    return context


def select_user_context(
    session: Session,
    user: User,
    payload: UserContextUpdate,
) -> UserContextResponse:
    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == payload.workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise DomainError("Workspace not found", "workspace_not_found", 404)

    set_tenant_context(session, payload.workspace_id)
    repository: Repository | None = None
    if payload.repository_id is not None:
        repository = session.scalar(
            select(Repository).where(
                Repository.id == payload.repository_id,
                Repository.workspace_id == payload.workspace_id,
            )
        )
        if repository is None:
            raise DomainError(
                "Repository not found", "repository_not_found", 404
            )

    scenario: Scenario | None = None
    if payload.scenario_id is not None:
        scenario_statement = select(Scenario).where(
            Scenario.id == payload.scenario_id,
            Scenario.workspace_id == payload.workspace_id,
        )
        if repository is not None:
            scenario_statement = scenario_statement.where(
                Scenario.repository_id == repository.id
            )
        scenario = session.scalar(scenario_statement)
        if scenario is None:
            raise DomainError("Scenario not found", "scenario_not_found", 404)
        if repository is None:
            repository = session.get(Repository, scenario.repository_id)

    context = session.get(UserContext, user.id)
    if context is None:
        context = UserContext(
            user_id=user.id,
            workspace_id=payload.workspace_id,
            repository_id=repository.id if repository is not None else None,
            scenario_id=scenario.id if scenario is not None else None,
            updated_at=now_utc(),
        )
        session.add(context)
    else:
        context.workspace_id = payload.workspace_id
        context.repository_id = (
            repository.id if repository is not None else None
        )
        context.scenario_id = scenario.id if scenario is not None else None
        context.updated_at = now_utc()
    session.commit()
    return _context_response(context)


def activate_context_scenario(
    session: Session,
    scope: TenantScope,
    scenario: Scenario,
) -> UserContext:
    context = session.get(UserContext, scope.user.id)
    if context is None:
        raise DomainError(
            "Select or create a workspace first",
            "workspace_context_required",
            409,
        )
    context.workspace_id = scenario.workspace_id
    context.repository_id = scenario.repository_id
    context.scenario_id = scenario.id
    context.updated_at = now_utc()
    session.commit()
    return context


def resolve_tenant_scope(
    session: Session,
    user: User,
    *,
    minimum_role: str = "viewer",
    allow_legacy_bootstrap: bool = False,
) -> TenantScope:
    context = ensure_context(
        session,
        user,
        allow_legacy_bootstrap=allow_legacy_bootstrap,
    )
    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == context.workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise DomainError("Workspace not found", "workspace_not_found", 404)
    if ROLE_LEVEL[membership.role] < ROLE_LEVEL[minimum_role]:
        raise DomainError(
            "You do not have permission for this action",
            "forbidden",
            403,
        )
    set_tenant_context(session, context.workspace_id)
    return TenantScope(
        user=user,
        workspace_id=context.workspace_id,
        repository_id=context.repository_id,
        scenario_id=context.scenario_id,
        role=membership.role,
    )


def get_legacy_scope(
    request: Request,
    user: Annotated[User, Depends(get_legacy_user)],
    session: Annotated[Session, Depends(get_session)],
) -> TenantScope:
    return resolve_tenant_scope(
        session,
        user,
        allow_legacy_bootstrap=(
            request.app.state.settings.development_auth_available()
            and request.app.state.settings.seed_synthetic_data
        ),
    )


def require_responder_scope(
    scope: Annotated[TenantScope, Depends(get_legacy_scope)],
) -> TenantScope:
    if ROLE_LEVEL[scope.role] < ROLE_LEVEL["responder"]:
        raise DomainError(
            "You do not have permission for this action",
            "forbidden",
            403,
        )
    return scope
