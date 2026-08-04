"""Invitation email delivery owned by the supervised outbox worker."""

from __future__ import annotations

from email.message import EmailMessage
import smtplib
import ssl
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .provider_models import InvitationDelivery
from .models import Invitation
from .workspace_services import now_utc, token_digest


class InvitationDeliveryUncertain(RuntimeError):
    """SMTP may have accepted a message, so automatic retry would duplicate it."""


def record_local_invitation_delivery(
    session: Session,
    invitation_id: str,
    *,
    status: str,
) -> None:
    """Persist a non-provider development/disabled delivery outcome in the caller transaction."""

    session.add(
        InvitationDelivery(
            id=str(uuid4()),
            invitation_id=invitation_id,
            provider="development_outbox" if status == "development_outbox" else "disabled",
            status=status,
            provider_message_id=None,
            error_code=None,
            attempted_at=now_utc(),
        )
    )


def deliver_invitation_smtp(
    session: Session,
    invitation: Invitation,
    claim_token: str,
    settings: Settings,
) -> dict[str, str]:
    """Send one SMTP message while preventing a silent duplicate after a crash.

    SMTP has no portable idempotency primitive.  The durable record is committed
    as ``publishing`` before any provider I/O.  A later worker observing that
    state must stop for operator review instead of sending a second invite.
    """

    existing = session.scalar(
        select(InvitationDelivery)
        .where(InvitationDelivery.invitation_id == invitation.id)
        .order_by(InvitationDelivery.attempted_at.desc())
        .limit(1)
    )
    if existing is not None:
        if existing.status == "sent":
            return {"delivery_status": "sent", "invitation_id": invitation.id}
        raise InvitationDeliveryUncertain(
            f"invitation delivery is already in {existing.status!r} state"
        )

    delivery = InvitationDelivery(
        id=str(uuid4()),
        invitation_id=invitation.id,
        provider="smtp",
        status="publishing",
        provider_message_id=None,
        error_code=None,
        attempted_at=now_utc(),
    )
    session.add(delivery)
    # The token is derived only when the worker is ready to send.  If the
    # managed secret rotates while the job waits, the freshly derived token and
    # its stored digest remain a matching pair.
    invitation.token_hash = token_digest(claim_token)
    session.commit()

    invite_url = (
        f"{settings.frontend_public_url.rstrip('/')}"
        f"/accept-invite?token={claim_token}"
    )
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = invitation.email
    message["Subject"] = "You were invited to a DeployGuard workspace"
    message.set_content(
        "You have been invited to a DeployGuard workspace.\n\n"
        f"Accept the invitation: {invite_url}\n\n"
        f"This invitation expires at {invitation.expires_at.isoformat()}."
    )
    message.add_alternative(
        "<p>You have been invited to a DeployGuard workspace.</p>"
        f'<p><a href="{invite_url}">Accept invitation</a></p>'
        f"<p>This invitation expires at {invitation.expires_at.isoformat()}.</p>",
        subtype="html",
    )
    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=15
        ) as client:
            if settings.smtp_use_tls:
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        delivery.status = "failed"
        delivery.error_code = "provider_unavailable"
        session.commit()
        raise InvitationDeliveryUncertain(
            "SMTP delivery outcome is uncertain; issue a new invitation instead of retrying"
        ) from error

    delivery.status = "sent"
    delivery.error_code = None
    session.commit()
    return {"delivery_status": "sent", "invitation_id": invitation.id}
