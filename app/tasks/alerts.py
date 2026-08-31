# Refactor of the existing alert-dispatch logic (app.core.email.send_alert_email)
# into a Celery task, so the outbound SMTP call runs on a worker instead of
# blocking the FastAPI request thread. Nothing about the send logic itself
# changes — this is the same function your app already uses, just invoked
# via .delay()/.apply_async() instead of a direct call.

from app.core.celery_app import celery_app
from app.core.email import send_alert_email


@celery_app.task(
    name="app.tasks.alerts.send_alert_email_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def send_alert_email_task(self, subject: str, body: str, to: str | None = None) -> dict:
    """
    Background wrapper around send_alert_email.
    Note on behavior: send_alert_email() is written to never raise — it
    swallows SMTP errors internally and just logs them (see its docstring:
    "a mail-server hiccup should not break the request that triggered the
    alert"). That means this task will report SUCCESS to Celery even if the
    underlying send failed, exactly like it did in the synchronous path.
    The max_retries/default_retry_delay above are wired up in case you
    later want send_alert_email to raise on failure so Celery can retry it —
    as written today they won't trigger, since nothing escapes the function
    to catch. Flagging this so the retry behavior isn't assumed silently.
    """
    send_alert_email(subject=subject, body=body, to=to)
    return {"status": "dispatched", "subject": subject, "to": to}