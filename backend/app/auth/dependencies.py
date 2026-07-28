import hashlib
from collections.abc import Generator
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import DomainError
from ..models import User
from ..workspace_services import authenticate_token, normalize_email, now_utc
from .oidc import OIDCIdentity, OIDCVerifier


bearer = HTTPBearer(auto_error=False)


def get_session(request: Request) -> Generator[Session, None, None]:
    yield from request.app.state.database.session()


def _authentication_required() -> DomainError:
    return DomainError(
        "Authentication is required",
        "authentication_required",
        401,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _oidc_subject(identity: OIDCIdentity) -> str:
    digest = hashlib.sha256(
        f"{identity.issuer}\0{identity.subject}".encode("utf-8")
    ).hexdigest()
    return f"oidc:{digest}"


def _synchronize_oidc_user(
    session: Session, identity: OIDCIdentity
) -> User:
    provider_subject = _oidc_subject(identity)
    user = session.scalar(
        select(User).where(User.provider_subject == provider_subject)
    )
    if user is None:
        conflicting_email = session.scalar(
            select(User).where(User.email == identity.email)
        )
        if conflicting_email is not None:
            raise DomainError(
                "This email is already associated with another identity",
                "identity_email_conflict",
                409,
            )
        user = User(
            id=str(uuid4()),
            email=identity.email,
            display_name=identity.display_name,
            auth_provider="oidc",
            provider_subject=provider_subject,
            is_active=True,
            created_at=now_utc(),
        )
        session.add(user)
        session.commit()
    elif (
        user.email != identity.email
        or user.display_name != identity.display_name
    ):
        conflicting_email = session.scalar(
            select(User).where(
                User.email == identity.email,
                User.id != user.id,
            )
        )
        if conflicting_email is not None:
            raise DomainError(
                "This email is already associated with another identity",
                "identity_email_conflict",
                409,
            )
        user.email = identity.email
        user.display_name = identity.display_name
        session.commit()
    if not user.is_active:
        raise DomainError("User is inactive", "user_inactive", 403)
    return user


def ensure_development_user(
    session: Session,
    *,
    email: str,
    display_name: str,
) -> User:
    normalized_email = normalize_email(email)
    provider_subject = f"development:{normalized_email}"
    user = session.scalar(
        select(User).where(User.provider_subject == provider_subject)
    )
    if user is None:
        conflicting_email = session.scalar(
            select(User).where(User.email == normalized_email)
        )
        if conflicting_email is not None:
            return conflicting_email
        user = User(
            id=str(uuid4()),
            email=normalized_email,
            display_name=display_name.strip() or normalized_email.split("@")[0],
            auth_provider="development",
            provider_subject=provider_subject,
            is_active=True,
            created_at=now_utc(),
        )
        session.add(user)
        session.commit()
    if not user.is_active:
        raise DomainError("User is inactive", "user_inactive", 403)
    return user


def resolve_authenticated_user(
    request: Request,
    session: Session,
    credentials: HTTPAuthorizationCredentials | None,
) -> User:
    settings = request.app.state.settings
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_required()
    if settings.auth_provider == "development":
        if not settings.development_auth_available():
            raise _authentication_required()
        return authenticate_token(session, credentials.credentials)
    if settings.auth_provider == "oidc":
        verifier: OIDCVerifier = request.app.state.oidc_verifier
        return _synchronize_oidc_user(
            session, verifier.verify(credentials.credentials)
        )
    raise _authentication_required()


def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer)
    ],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    return resolve_authenticated_user(request, session, credentials)


def get_legacy_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer)
    ],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    settings = request.app.state.settings
    if credentials is not None:
        return resolve_authenticated_user(request, session, credentials)
    if settings.development_auth_available():
        return ensure_development_user(
            session,
            email=settings.development_user_email,
            display_name=settings.development_user_name,
        )
    raise _authentication_required()

