import uuid, enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# Enum defining the three site-wide roles a user can have.
class GlobalRole(str, enum.Enum):
    admin = "admin"
    member = "member"

# Table representing application users; stores authentication data, one global role, and relationships to owned/member projects, tasks, and comments.
class User(Base):
    __tablename__ = "users"

    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Required user's display name.
    name = Column(String, nullable=False)

    # Required unique email address, with a database index for efficient lookup.
    email = Column(String, unique=True, nullable=False, index=True)

    # Required password hash; the plaintext password should never be stored here.
    password_hash = Column(String, nullable=False)

    # Required site-wide role, defaulting to the normal member role.
    global_role = Column(Enum(GlobalRole), default=GlobalRole.member, nullable=False)

    # Timestamp recording when the user account was created.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ORM relationship exposing projects owned directly by this user.
    owned_projects = relationship("Project", back_populates="owner")

    # ORM relationship exposing this user's project membership records.
    memberships = relationship("ProjectMember", back_populates="user")

    # ORM relationship exposing tasks created by this user.
    created_tasks = relationship("Task", back_populates="creator")

    # ORM relationship exposing comments authored by this user.
    comments = relationship("Comment", back_populates="author")