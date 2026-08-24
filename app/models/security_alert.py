import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base


# Append-only audit table for security-sensitive events such as unauthorized global-role changes.
class SecurityAlert(Base):
    """
    Append-only audit log for security-sensitive events — right now just
    unauthorized attempts to change a user's global role. Written to on
    every offending attempt regardless of how it's surfaced to the admin
    (console log today, a /notifications endpoint later — both read from
    this same table, so adding the endpoint is just a GET route away).
    """
    __tablename__ = "security_alerts"

    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Required string identifying what type of security event occurred.
    alert_type = Column(String, nullable=False)

    # Required human-readable description of the security event.
    message = Column(Text, nullable=False)

    # Required foreign key identifying the authenticated user who performed the action.
    actor_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Optional plain string identifying the target, deliberately not a foreign key so invalid target IDs cannot break alert logging.
    target_user_id = Column(String(36), nullable=True)

    # Timestamp recording when the security event was logged.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Boolean indicating whether an administrator has resolved the alert, defaulting to unresolved.
    resolved = Column(Boolean, default=False, nullable=False)

    # ORM relationship connecting the alert to the authenticated user who caused it.
    actor = relationship("User")