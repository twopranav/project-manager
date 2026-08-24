import logging
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.security_alert import SecurityAlert

# Dedicated logger so this is easy to route/filter separately later
# (e.g. to its own log file, or a handler that fires an email/webhook)
# without touching call sites.
logger = logging.getLogger("security")


def log_unauthorized_role_change(
    db: Session,
    actor: User,
    target_user_id: str,
    attempted_role: str,
) -> None:
    """
    Record a rejected attempt to change a user's global_role by someone
    who isn't the admin. Writes to both the console (immediate visibility)
    and the security_alerts table (durable, queryable — this is the same
    row a future GET /admin/alerts / notifications tab would read from).
    """
    message = (
        f"Unauthorized global role change attempt: user {actor.email} "
        f"(id={actor.id}, role={actor.global_role.value}) tried to set "
        f"user id={target_user_id} to global_role={attempted_role}."
    )

    logger.warning(message)

    alert = SecurityAlert(
        alert_type="unauthorized_global_role_change",
        message=message,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
    )
    db.add(alert)
    db.commit()
