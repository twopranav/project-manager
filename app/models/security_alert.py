import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class SecurityAlert(Base):
    """
    Append-only audit log for security-sensitive events — right now just
    unauthorized attempts to change a user's global role. Written to on
    every offending attempt regardless of how it's surfaced to the admin
    (console log today, a /notifications endpoint later — both read from
    this same table, so adding the endpoint is just a GET route away).
    """
    __tablename__ = "security_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type = Column(String, nullable=False)  # e.g. "unauthorized_global_role_change"
    message = Column(Text, nullable=False)

    # Who tried to do the thing. Real FK — this is always an authenticated,
    # already-existing user (get_current_user guarantees that).
    actor_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Who they tried to do it to. Plain string, NOT a FK — deliberately, so
    # logging an attempted attack on a bogus/mistyped user id can never
    # itself fail with a constraint error and swallow the alert.
    target_user_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved = Column(Boolean, default=False, nullable=False)

    actor = relationship("User")
