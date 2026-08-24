import uuid, enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# Enum defining the four project-specific permission levels a member can have.
class ProjectRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    contributor = "contributor"
    viewer = "viewer"

# Join table connecting users to projects while storing each user's project-specific role.
class ProjectMember(Base):
    __tablename__ = "project_members"

    # Enforce at the database level that a user can have only one membership row per project.
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_user_project"),)

    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Required foreign key identifying the project being joined.
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)

    # Required foreign key identifying the user joining the project.
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Required project-specific role, defaulting to contributor.
    project_role = Column(Enum(ProjectRole), default=ProjectRole.contributor, nullable=False)

    # Timestamp recording when the user joined the project.
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ORM relationship connecting this membership to its Project.
    project = relationship("Project", back_populates="members")

    # ORM relationship connecting this membership to its User.
    user = relationship("User", back_populates="memberships")