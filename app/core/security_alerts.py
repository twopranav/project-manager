import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.security_alert import SecurityAlert
from app.core.email import send_alert_email
from app.core.redis_client import redis_client
from app.tasks.alerts import send_alert_email_task

# Create a dedicated security logger so security events can later be routed or filtered independently.
logger = logging.getLogger("security")

# Alert types that also send an email to ALERT_ADMIN_EMAIL, on top of always
# being written to the security_alerts table. Anything not listed here stays
# log-only (visible via GET /admin/alerts, no email sent).
EMAIL_ENABLED_ALERT_TYPES = {
    "unauthorized_global_role_change",
    "admin_transfer_success",
    "repeated_403",
    "repeated_failed_login",
}

# For alert types where a single actor could realistically trigger many
# rapid events (an attacker scripting requests — not a one-off legitimate
# action like an admin transfer), cap emails to one per actor per window
# instead of one per event. Checked centrally in log_security_alert via a
# Redis SETNX cooldown key, so any alert type gets this by just adding an
# entry here — no per-alert-type dedup logic needed elsewhere.
# admin_transfer_success has no entry: it requires already being admin, so
# it can't realistically be spammed, and every occurrence is worth its own
# email regardless of timing.
EMAIL_COOLDOWN_WINDOW: dict[str, timedelta] = {
    "unauthorized_global_role_change": timedelta(minutes=10),
}

# How repeated-403 detection works: every access-denied response logs a
# (log-only) "access_denied" row, and increments a Redis counter keyed to
# the actor with a TTL of REPEATED_403_WINDOW. The first denial in a window
# starts the TTL; every denial after that just increments. The moment the
# counter hits REPEATED_403_THRESHOLD exactly, we fire one emailed
# "repeated_403" alert. Because the counter resets when its TTL expires,
# this naturally rate-limits to at most one alert per actor per window —
# same behavior as before, just driven by a Redis TTL instead of a rolling
# DB query on every single denial.
REPEATED_403_THRESHOLD = 5
REPEATED_403_WINDOW = timedelta(minutes=10)

# Same pattern, for failed logins against a *known* account (see
# log_failed_login_attempt below for why unknown emails can't be counted
# this way).
REPEATED_FAILED_LOGIN_THRESHOLD = 5
REPEATED_FAILED_LOGIN_WINDOW = timedelta(minutes=10)

EMAIL_COOLDOWN_WINDOW["repeated_403"] = REPEATED_403_WINDOW
EMAIL_COOLDOWN_WINDOW["repeated_failed_login"] = REPEATED_FAILED_LOGIN_WINDOW


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
    then queues an email too if alert_type is email-enabled. Every other
    alert-logging helper in this module is a thin wrapper around this.

    Email dispatch always writes the DB row first regardless of what happens
    next — if alert_type has a cooldown window (see EMAIL_COOLDOWN_WINDOW)
    and one is already active for this actor, the row is still logged but no
    email is sent. This is the single choke point for alert-email spam
    protection across all alert types, so a new emailed alert type only
    needs an EMAIL_COOLDOWN_WINDOW entry, not its own dedup logic.
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
        cooldown = EMAIL_COOLDOWN_WINDOW.get(alert_type)
        if cooldown is not None:
            cooldown_key = f"alert_cooldown:{alert_type}:{actor.id}"
            # SETNX-with-TTL: atomic, so two concurrent requests can't both
            # win the cooldown and both email — only the first caller past
            # the gate in this window gets through.
            acquired = redis_client.set(cooldown_key, "1", nx=True, ex=int(cooldown.total_seconds()))
            if not acquired:
                return alert  # already alerted for this actor within the window

        # Dispatched via Celery instead of calling send_alert_email directly,
        # so the SMTP call runs on the worker rather than blocking this
        # request. Note: send_alert_email() never raises internally (it
        # swallows and logs SMTP errors), so this task always reports
        # SUCCESS to Celery even if the send itself failed — same
        # best-effort behavior as before, just off the request thread.
        send_alert_email_task.delay(subject=f"[Security Alert] {alert_type}", body=message)

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

    Every attempt is still logged to the DB regardless of email cooldown —
    only the email itself is capped to one per actor per
    EMAIL_COOLDOWN_WINDOW["unauthorized_global_role_change"] (see
    log_security_alert), so a scripted burst of attempts can't spam the
    inbox the way it could before.
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
    Record a failed login (wrong password) for a *known* account. A single
    failed login stays log-only — a mistyped password is common and not
    itself alarming — but repeated failures against the same account within
    REPEATED_FAILED_LOGIN_WINDOW now escalate to one emailed
    "repeated_failed_login" alert, same rate-limited pattern as repeated_403.

    Note: we can only track this when the email matches a real account — a
    login attempt against an email that doesn't exist has no valid
    actor_user_id to attach to or count against, so those aren't covered
    here. That's a separate gap (would need IP-keyed counting instead of
    actor-keyed) and isn't part of this change.
    """
    message = f"Failed login attempt for account {actor.email} (id={actor.id})."
    log_security_alert(
        db=db,
        alert_type="failed_login_attempt",
        message=message,
        actor=actor,
        target_user_id=actor.id,
    )

    count_key = f"failed_login_count:{actor.id}"
    window_s = int(REPEATED_FAILED_LOGIN_WINDOW.total_seconds())
    attempt_count = redis_client.incr(count_key)
    if attempt_count == 1:
        redis_client.expire(count_key, window_s)

    # Fire exactly on the threshold crossing, not >=, so this only logs +
    # emails once per window instead of on every attempt past the threshold.
    if attempt_count != REPEATED_FAILED_LOGIN_THRESHOLD:
        return

    log_security_alert(
        db=db,
        alert_type="repeated_failed_login",
        message=(
            f"Repeated failed login attempts: account {actor.email} "
            f"(id={actor.id}) had {attempt_count} failed logins in the last "
            f"{window_s // 60} minutes."
        ),
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
    Always logs a log-only "access_denied" row, then increments a Redis
    counter for this actor (TTL'd to REPEATED_403_WINDOW). The moment the
    counter hits REPEATED_403_THRESHOLD exactly, fires one emailed
    "repeated_403" alert — the counter's own TTL is what prevents firing
    again until the window rolls over, so no separate "already alerted"
    check is needed here anymore (that's now handled centrally in
    log_security_alert via EMAIL_COOLDOWN_WINDOW).
    """
    log_security_alert(
        db=db,
        alert_type="access_denied",
        message=f"Access denied for {actor.email} (id={actor.id}): {detail}",
        actor=actor,
    )

    count_key = f"denial_count:{actor.id}"
    window_s = int(REPEATED_403_WINDOW.total_seconds())
    denial_count = redis_client.incr(count_key)
    if denial_count == 1:
        redis_client.expire(count_key, window_s)

    # Fire exactly on the threshold crossing, not >=, so this only logs +
    # emails once per window instead of on every denial past the threshold.
    if denial_count != REPEATED_403_THRESHOLD:
        return

    log_security_alert(
        db=db,
        alert_type="repeated_403",
        message=(
            f"Repeated access-denied responses: {actor.email} (id={actor.id}) "
            f"hit {denial_count} permission denials in the last "
            f"{window_s // 60} minutes."
        ),
        actor=actor,
    )