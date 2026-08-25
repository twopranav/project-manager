import logging
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.security_alert import SecurityAlert

# Create a dedicated security logger so security events can later be routed or filtered independently.
logger = logging.getLogger("security")


# Record an unauthorized global-role change attempt both in logs and in the persistent security-alert table.
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
    # Build a human-readable message describing who attempted the unauthorized role change and what they attempted.
    message = (
        f"Unauthorized global role change attempt: user {actor.email} "
        f"(id={actor.id}, role={actor.global_role.value}) tried to set "
        f"user id={target_user_id} to global_role={attempted_role}."
    )
    # Write the security event to the application's security logger for immediate visibility.
    logger.warning(message)
    # Build a persistent SecurityAlert record containing the details of the rejected action.
    alert = SecurityAlert(
        alert_type="unauthorized_global_role_change",
        message=message,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
    )
    # Stage the security alert for insertion into the database, then commit
    db.add(alert)
    db.commit()