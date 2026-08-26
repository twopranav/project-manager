import logging
import smtplib
from email.message import EmailMessage
from app.core.config import get_settings

logger = logging.getLogger("security")

settings = get_settings()


def send_alert_email(subject: str, body: str) -> None:
    """
    Best-effort SMTP send for a security-alert notification. Never raises —
    a mail-server hiccup should not break the request that triggered the
    alert (the alert is already durably written to security_alerts before
    this is ever called). If SMTP isn't configured (no SMTP_HOST or no
    ALERT_ADMIN_EMAIL), this just logs and returns, so alert-emailing is
    opt-in via env vars rather than a hard requirement to run the app.
    """
    if not settings.SMTP_HOST or not settings.ALERT_ADMIN_EMAIL:
        logger.info(
            "Alert email skipped (SMTP_HOST/ALERT_ADMIN_EMAIL not configured): %s",
            subject,
        )
        return

    recipients = [addr.strip() for addr in settings.ALERT_ADMIN_EMAIL.split(",") if addr.strip()]
    from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)
    except Exception:
        # Swallow any SMTP failure (auth error, connection refused, timeout,
        # etc.) — the alert itself is already saved in the DB regardless.
        logger.exception("Failed to send alert email: %s", subject)