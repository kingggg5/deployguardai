from email.message import EmailMessage
import smtplib
import ssl
from uuid import uuid4

from sqlalchemy.orm import Session

from .config import Settings
from .provider_models import InvitationDelivery
from .schemas import InvitationCreated
from .workspace_services import now_utc


def deliver_invitation(
    session: Session,
    invitation: InvitationCreated,
    settings: Settings,
) -> InvitationCreated:
    mode = settings.email_delivery_mode()
    if mode == "development_outbox":
        _record(session, invitation.id, mode, "development_outbox")
        return invitation.model_copy(
            update={
                "delivery_mode": mode,
                "delivery_status": "development_outbox",
            }
        )
    if mode == "disabled":
        _record(session, invitation.id, mode, "disabled")
        return invitation.model_copy(
            update={
                "delivery_mode": mode,
                "delivery_status": "disabled",
                "claim_token": None,
                "accept_path": None,
            }
        )

    invite_url = (
        f"{settings.frontend_public_url.rstrip('/')}"
        f"/accept-invite?token={invitation.claim_token}"
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
        _record(session, invitation.id, "smtp", "sent")
        status = "sent"
    except (OSError, smtplib.SMTPException):
        _record(session, invitation.id, "smtp", "failed", "provider_unavailable")
        status = "failed"
    return invitation.model_copy(
        update={
            "delivery_mode": "smtp",
            "delivery_status": status,
            "claim_token": None,
            "accept_path": None,
        }
    )


def _record(
    session: Session,
    invitation_id: str,
    provider: str,
    status: str,
    error_code: str | None = None,
) -> None:
    session.add(
        InvitationDelivery(
            id=str(uuid4()),
            invitation_id=invitation_id,
            provider=provider,
            status=status,
            provider_message_id=None,
            error_code=error_code,
            attempted_at=now_utc(),
        )
    )
    session.commit()
