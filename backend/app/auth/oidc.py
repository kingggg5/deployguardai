from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from ..config import Settings
from ..errors import DomainError


@dataclass(frozen=True)
class OIDCIdentity:
    issuer: str
    subject: str
    email: str
    email_verified: bool
    display_name: str


class OIDCVerifier:
    """Validate OIDC access tokens without trusting unverified claims."""

    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.oidc_issuer.rstrip("/")
        self._audience = settings.oidc_audience
        self._algorithms = tuple(settings.oidc_algorithms)
        self._leeway = settings.oidc_leeway_seconds
        self._jwks = PyJWKClient(settings.oidc_jwks_url)

    def verify(self, token: str) -> OIDCIdentity:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={
                    "require": ["aud", "exp", "iat", "iss", "sub"],
                },
            )
        except (PyJWTError, PyJWKClientError, ValueError):
            raise DomainError(
                "Invalid or expired access token",
                "invalid_access_token",
                401,
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        email = str(claims.get("email", "")).strip().lower()
        if not email or "@" not in email:
            raise DomainError(
                "The identity token does not contain an email address",
                "oidc_email_required",
                401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        email_verified = claims.get("email_verified") is True
        if not email_verified:
            raise DomainError(
                "A verified email address is required",
                "oidc_email_not_verified",
                401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        display_name = str(
            claims.get("name")
            or claims.get("preferred_username")
            or email.split("@", 1)[0]
        ).strip()
        return OIDCIdentity(
            issuer=str(claims["iss"]),
            subject=str(claims["sub"]),
            email=email,
            email_verified=True,
            display_name=display_name[:160],
        )

