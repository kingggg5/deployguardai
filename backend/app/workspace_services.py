import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import DomainError
from .models import (
    AccessToken,
    AuditEvent,
    Invitation,
    Repository,
    User,
    UserContext,
    Workspace,
    WorkspaceMembership,
)
from .rls import set_tenant_context
from .schemas import (
    AuditEventSummary,
    InvitationCreate,
    InvitationCreated,
    InvitationSummary,
    MembershipSummary,
    RepositoryCreate,
    RepositorySummary,
    SessionResponse,
    UserSummary,
    WorkspaceCreate,
    WorkspaceSummary,
)


ROLE_LEVEL = {"viewer": 10, "responder": 20, "admin": 30, "owner": 40}


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def user_summary(user: User) -> UserSummary:
    return UserSummary.model_validate(user)


def workspace_summary(
    session: Session, membership: WorkspaceMembership
) -> WorkspaceSummary:
    workspace = membership.workspace
    set_tenant_context(session, workspace.id)
    repository_count = session.scalar(
        select(func.count(Repository.id)).where(
            Repository.workspace_id == workspace.id
        )
    )
    member_count = session.scalar(
        select(func.count(WorkspaceMembership.id)).where(
            WorkspaceMembership.workspace_id == workspace.id
        )
    )
    return WorkspaceSummary(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        role=membership.role,
        repository_count=repository_count or 0,
        member_count=member_count or 0,
        created_at=workspace.created_at,
    )


def list_user_workspaces(
    session: Session, user: User
) -> list[WorkspaceSummary]:
    memberships = session.scalars(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(WorkspaceMembership.joined_at)
    ).all()
    return [workspace_summary(session, item) for item in memberships]


def create_development_session(
    session: Session,
    *,
    email: str,
    display_name: str,
    token_ttl_hours: int,
) -> SessionResponse:
    normalized_email = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        user = User(
            id=new_id(),
            email=normalized_email,
            display_name=display_name.strip() or normalized_email.split("@")[0],
            auth_provider="development",
            provider_subject=f"development:{normalized_email}",
            is_active=True,
            created_at=now_utc(),
        )
        session.add(user)
        session.flush()
    if not user.is_active:
        raise DomainError("User is inactive", "user_inactive", 403)

    raw_token = secrets.token_urlsafe(32)
    expires_at = now_utc() + timedelta(hours=token_ttl_hours)
    session.add(
        AccessToken(
            id=new_id(),
            user_id=user.id,
            token_hash=token_digest(raw_token),
            provider="development",
            created_at=now_utc(),
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    session.commit()
    return SessionResponse(
        access_token=raw_token,
        token_type="bearer",
        expires_at=expires_at,
        provider="development",
        user=user_summary(user),
        workspaces=list_user_workspaces(session, user),
    )


def authenticate_token(session: Session, token: str) -> User:
    access_token = session.scalar(
        select(AccessToken).where(AccessToken.token_hash == token_digest(token))
    )
    if (
        access_token is None
        or access_token.revoked_at is not None
        or access_token.expires_at.replace(tzinfo=UTC) <= now_utc()
    ):
        raise DomainError("Invalid or expired access token", "invalid_access_token", 401)
    user = session.get(User, access_token.user_id)
    if user is None or not user.is_active:
        raise DomainError("Invalid or expired access token", "invalid_access_token", 401)
    return user


def membership_for(
    session: Session,
    user: User,
    workspace_id: str,
    minimum_role: str = "viewer",
) -> WorkspaceMembership:
    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise DomainError("Workspace not found", "workspace_not_found", 404)
    if ROLE_LEVEL[membership.role] < ROLE_LEVEL[minimum_role]:
        raise DomainError(
            "You do not have permission for this action", "forbidden", 403
        )
    set_tenant_context(session, workspace_id)
    return membership


def audit(
    session: Session,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    request_id: str,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            id=new_id(),
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            event_metadata=metadata or {},
            created_at=now_utc(),
        )
    )


def create_workspace(
    session: Session,
    user: User,
    payload: WorkspaceCreate,
    request_id: str,
) -> WorkspaceSummary:
    slug = payload.slug.strip().lower()
    if session.scalar(select(Workspace.id).where(Workspace.slug == slug)):
        raise DomainError("Workspace slug is already in use", "workspace_slug_exists", 409)
    timestamp = now_utc()
    workspace = Workspace(
        id=new_id(),
        name=payload.name.strip(),
        slug=slug,
        created_by_user_id=user.id,
        created_at=timestamp,
        updated_at=timestamp,
    )
    membership = WorkspaceMembership(
        id=new_id(),
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
        joined_at=timestamp,
    )
    workspace.memberships.append(membership)
    session.add(workspace)
    context = session.get(UserContext, user.id)
    if context is None:
        session.add(
            UserContext(
                user_id=user.id,
                workspace_id=workspace.id,
                repository_id=None,
                scenario_id=None,
                updated_at=timestamp,
            )
        )
    set_tenant_context(session, workspace.id)
    audit(
        session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        action="workspace.created",
        resource_type="workspace",
        resource_id=workspace.id,
        request_id=request_id,
        metadata={"slug": slug},
    )
    session.commit()
    return workspace_summary(session, membership)


def create_repository(
    session: Session,
    user: User,
    workspace_id: str,
    payload: RepositoryCreate,
    request_id: str,
) -> RepositorySummary:
    membership_for(session, user, workspace_id, "admin")
    full_name = payload.full_name.strip()
    provider_id = f"fixture:{full_name.lower()}"
    existing = session.scalar(
        select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.provider == "development",
            Repository.provider_repository_id == provider_id,
        )
    )
    if existing is not None:
        raise DomainError(
            "Repository is already connected", "repository_already_connected", 409
        )
    timestamp = now_utc()
    repository = Repository(
        id=new_id(),
        workspace_id=workspace_id,
        provider="development",
        provider_repository_id=provider_id,
        full_name=full_name,
        default_branch=payload.default_branch.strip(),
        visibility=payload.visibility,
        connection_state="connected",
        data_mode="synthetic",
        selected=True,
        last_synced_at=timestamp,
        created_at=timestamp,
    )
    session.add(repository)
    session.flush()
    context = session.get(UserContext, user.id)
    if (
        context is not None
        and context.workspace_id == workspace_id
        and context.repository_id is None
    ):
        context.repository_id = repository.id
        context.updated_at = timestamp
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="repository.connected",
        resource_type="repository",
        resource_id=repository.id,
        request_id=request_id,
        metadata={"provider": "development", "full_name": full_name},
    )
    session.commit()
    return RepositorySummary.model_validate(repository)


def list_repositories(
    session: Session, user: User, workspace_id: str
) -> list[RepositorySummary]:
    membership_for(session, user, workspace_id)
    records = session.scalars(
        select(Repository)
        .where(Repository.workspace_id == workspace_id)
        .order_by(Repository.full_name)
    ).all()
    return [RepositorySummary.model_validate(record) for record in records]


def list_members(
    session: Session, user: User, workspace_id: str
) -> list[MembershipSummary]:
    membership_for(session, user, workspace_id)
    memberships = session.scalars(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.joined_at)
    ).all()
    return [
        MembershipSummary(
            user=user_summary(item.user),
            role=item.role,
            joined_at=item.joined_at,
        )
        for item in memberships
    ]


def create_invitation(
    session: Session,
    user: User,
    workspace_id: str,
    payload: InvitationCreate,
    request_id: str,
    ttl_hours: int,
) -> InvitationCreated:
    caller = membership_for(session, user, workspace_id, "admin")
    if payload.role == "admin" and caller.role != "owner":
        raise DomainError("Only owners can invite admins", "forbidden", 403)
    existing_user = session.scalar(select(User).where(User.email == payload.email))
    if existing_user and session.scalar(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == existing_user.id,
        )
    ):
        raise DomainError("User is already a member", "member_already_exists", 409)
    pending = session.scalar(
        select(Invitation).where(
            Invitation.workspace_id == workspace_id,
            Invitation.email == payload.email,
            Invitation.status == "pending",
            Invitation.expires_at > now_utc(),
        )
    )
    if pending:
        raise DomainError(
            "A pending invitation already exists",
            "invitation_already_pending",
            409,
        )
    raw_token = secrets.token_urlsafe(32)
    timestamp = now_utc()
    invitation = Invitation(
        id=new_id(),
        workspace_id=workspace_id,
        email=payload.email,
        role=payload.role,
        token_hash=token_digest(raw_token),
        status="pending",
        invited_by_user_id=user.id,
        created_at=timestamp,
        expires_at=timestamp + timedelta(hours=ttl_hours),
        accepted_at=None,
        revoked_at=None,
    )
    session.add(invitation)
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="invitation.created",
        resource_type="invitation",
        resource_id=invitation.id,
        request_id=request_id,
        metadata={"email": payload.email, "role": payload.role},
    )
    session.commit()
    return InvitationCreated(
        **InvitationSummary.model_validate(invitation).model_dump(),
        delivery_mode="development_outbox",
        delivery_status="development_outbox",
        claim_token=raw_token,
        accept_path=f"/accept-invite?token={raw_token}",
    )


def invitation_summary(record: Invitation) -> InvitationSummary:
    status = record.status
    if status == "pending" and record.expires_at.replace(tzinfo=UTC) <= now_utc():
        status = "expired"
    return InvitationSummary(
        id=record.id,
        workspace_id=record.workspace_id,
        email=record.email,
        role=record.role,
        status=status,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


def list_invitations(
    session: Session, user: User, workspace_id: str
) -> list[InvitationSummary]:
    membership_for(session, user, workspace_id, "admin")
    records = session.scalars(
        select(Invitation)
        .where(Invitation.workspace_id == workspace_id)
        .order_by(Invitation.created_at.desc())
    ).all()
    return [invitation_summary(record) for record in records]


def revoke_invitation(
    session: Session,
    user: User,
    workspace_id: str,
    invitation_id: str,
    request_id: str,
) -> InvitationSummary:
    membership_for(session, user, workspace_id, "admin")
    invitation = session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.workspace_id == workspace_id,
        )
    )
    if invitation is None:
        raise DomainError("Invitation not found", "invitation_not_found", 404)
    if invitation.status != "pending":
        raise DomainError("Invitation is not pending", "invitation_not_pending", 409)
    invitation.status = "revoked"
    invitation.revoked_at = now_utc()
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="invitation.revoked",
        resource_type="invitation",
        resource_id=invitation.id,
        request_id=request_id,
    )
    session.commit()
    return invitation_summary(invitation)


def accept_invitation(
    session: Session,
    user: User,
    raw_token: str,
    request_id: str,
) -> WorkspaceSummary:
    invitation = session.scalar(
        select(Invitation).where(Invitation.token_hash == token_digest(raw_token))
    )
    invalid = (
        invitation is None
        or invitation.status != "pending"
        or invitation.revoked_at is not None
        or invitation.expires_at.replace(tzinfo=UTC) <= now_utc()
        or invitation.email != user.email
    )
    if invalid:
        raise DomainError("Invitation is invalid", "invalid_invitation", 400)
    set_tenant_context(session, invitation.workspace_id)
    existing = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == invitation.workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if existing is None:
        existing = WorkspaceMembership(
            id=new_id(),
            workspace_id=invitation.workspace_id,
            user_id=user.id,
            role=invitation.role,
            joined_at=now_utc(),
        )
        session.add(existing)
    context = session.get(UserContext, user.id)
    if context is None:
        context = UserContext(
            user_id=user.id,
            workspace_id=invitation.workspace_id,
            repository_id=None,
            scenario_id=None,
            updated_at=now_utc(),
        )
        session.add(context)
    invitation.status = "accepted"
    invitation.accepted_at = now_utc()
    audit(
        session,
        workspace_id=invitation.workspace_id,
        actor_user_id=user.id,
        action="invitation.accepted",
        resource_type="invitation",
        resource_id=invitation.id,
        request_id=request_id,
        metadata={"role": invitation.role},
    )
    session.commit()
    return workspace_summary(session, existing)


def list_audit_events(
    session: Session, user: User, workspace_id: str, limit: int
) -> list[AuditEventSummary]:
    membership_for(session, user, workspace_id, "admin")
    records = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.workspace_id == workspace_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    ).all()
    return [AuditEventSummary.model_validate(record) for record in records]
