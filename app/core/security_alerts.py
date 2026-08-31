import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.security_alert import SecurityAlert
from app.core.email import send_alert_email

# Create a dedicated security logger so security events can later be routed or filtered independently.
logger = logging.getLogger("security")

# Alert types that also send an email to ALERT_ADMIN_EMAIL, on top of always
# being written to the security_alerts table. Anything not listed here stays
# log-only (visible via GET /admin/alerts, no email sent).
EMAIL_ENABLED_ALERT_TYPES = {
    "unauthorized_global_role_change",
    "admin_transfer_success",
    "repeated_403",
}

# How repeated-403 detection works: every access-denied response logs a
# (log-only) "access_denied" row. If the same actor racks up REPEATED_403_THRESHOLD
# of those within REPEATED_403_WINDOW, we fire one emailed "repeated_403" alert —
# then wait REPEATED_403_WINDOW again before firing another, so a user who's
# just confused about permissions doesn't trigger an email per click.
REPEATED_403_THRESHOLD = 5
REPEATED_403_WINDOW = timedelta(minutes=10)


def log_security_alert(
    db: Session,
    alert_type: str,
    message: str,
    actor: User,
    target_user_id: str | None = None,
    target_id: str | None = None,
) -> SecurityAlert:
    """
    Generic alert logger — writes to the console (immediate visibility) and
    to the security_alerts table (durable, queryable via GET /admin/alerts),
    then sends an email too if alert_type is email-enabled. Every other
    alert-logging helper in this module is a thin wrapper around this.
    """
    logger.warning(message)
    alert = SecurityAlert(
        alert_type=alert_type,
        message=message,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
        target_id=target_id,
    )
    db.add(alert)
    db.commit()

    if alert_type in EMAIL_ENABLED_ALERT_TYPES:
        # Best-effort — send_alert_email swallows its own SMTP errors, so a
        # dead mail server never breaks the request that triggered this.
        send_alert_email(subject=f"[Security Alert] {alert_type}", body=message)

    return alert


# Record an unauthorized global-role change attempt both in logs and in the persistent security-alert table.
def log_unauthorized_role_change(
    db: Session,
    actor: User,
    target_user_id: str,
    attempted_role: str,
) -> None:
    """
    Record a rejected attempt to change a user's global_role by someone
    who isn't the admin. This always fails at the permission layer — it's a
    log of the *attempt*, not an actual change — which is exactly why it's
    worth an email: it's either a confused user hitting an endpoint they
    found, or a possible privilege-escalation probe.
    """
    message = (
        f"Unauthorized global role change attempt: user {actor.email} "
        f"(id={actor.id}, role={actor.global_role.value}) tried to set "
        f"user id={target_user_id} to global_role={attempted_role}."
    )
    log_security_alert(
        db=db,
        alert_type="unauthorized_global_role_change",
        message=message,
        actor=actor,
        target_user_id=target_user_id,
    )


def log_admin_transfer_success(db: Session, actor: User, new_admin: User) -> None:
    """Record a successful site-admin handoff. Actor is the outgoing admin."""
    message = (
        f"Admin transfer: {actor.email} (id={actor.id}) transferred site-admin "
        f"rights to {new_admin.email} (id={new_admin.id})."
    )
    log_security_alert(
        db=db,
        alert_type="admin_transfer_success",
        message=message,
        actor=actor,
        target_user_id=new_admin.id,
    )


def log_project_deleted(
    db: Session,
    actor: User,
    project_id: str,
    project_name: str,
    manager: User | None = None,
) -> None:
    """
    Record any project deletion, regardless of whether the caller was the
    project's manager or the site admin — a global admin wants visibility
    into project deletions even when they're fully authorized. If a manager
    is supplied (and isn't the person doing the deleting), they also get a
    direct email notification separate from the admin alert log.
    """
    message = (
        f"Project deleted: '{project_name}' (id={project_id}) deleted by "
        f"{actor.email} (id={actor.id}, global_role={actor.global_role.value})."
    )
    log_security_alert(db=db, alert_type="project_deleted", message=message, actor=actor, target_id=project_id)
    if manager is not None:
        send_alert_email(
            subject=f"[Project Deleted] {project_name}",
            body=f"Your project '{project_name}' (id={project_id}) was deleted by {actor.email}.",
            to=manager.email,
        )


def log_failed_login_attempt(db: Session, actor: User) -> None:
    """
    Record a failed login (wrong password) for a *known* account. Log-only —
    not emailed, since a mistyped password is common and not itself alarming;
    it's the security_alerts table that gives an admin the option to notice
    a pattern later. Note: we can only log this when the email matches a
    real account — a login attempt against an email that doesn't exist has
    no valid actor_user_id to attach to, so those aren't logged here.
    """
    message = f"Failed login attempt for account {actor.email} (id={actor.id})."
    log_security_alert(
        db=db,
        alert_type="failed_login_attempt",
        message=message,
        actor=actor,
        target_user_id=actor.id,
    )


def log_access_denied_and_check_repeated(
    db: Session,
    actor: User,
    detail: str,
) -> None:
    """
    Call this right before raising a 403 on any permission-gated route.
    Always logs a log-only "access_denied" row, then checks whether this
    actor has crossed REPEATED_403_THRESHOLD such rows within
    REPEATED_403_WINDOW — if so (and we haven't already alerted for this
    actor in the current window), fires one emailed "repeated_403" alert.
    """
    log_security_alert(
        db=db,
        alert_type="access_denied",
        message=f"Access denied for {actor.email} (id={actor.id}): {detail}",
        actor=actor,
    )

    window_start = datetime.now(timezone.utc) - REPEATED_403_WINDOW

    recent_denials = (
        db.query(SecurityAlert)
        .filter(
            SecurityAlert.alert_type == "access_denied",
            SecurityAlert.actor_user_id == actor.id,
            SecurityAlert.created_at >= window_start,
        )
        .count()
    )
    if recent_denials < REPEATED_403_THRESHOLD:
        return

    already_alerted_recently = (
        db.query(SecurityAlert)
        .filter(
            SecurityAlert.alert_type == "repeated_403",
            SecurityAlert.actor_user_id == actor.id,
            SecurityAlert.created_at >= window_start,
        )
        .first()
    )
    if already_alerted_recently:
        return

    log_security_alert(
        db=db,
        alert_type="repeated_403",
        message=(
            f"Repeated access-denied responses: {actor.email} (id={actor.id}) "
            f"hit {recent_denials} permission denials in the last "
            f"{int(REPEATED_403_WINDOW.total_seconds() // 60)} minutes."
        ),
        actor=actor,
    )