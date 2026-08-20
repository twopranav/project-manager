import uuid, enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class ProjectRole(str, enum.Enum):
    admin = "admin"         
    manager = "manager"
    contributor = "contributor" 
    viewer = "viewer"

class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_user_project"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    project_role = Column(Enum(ProjectRole), default=ProjectRole.contributor, nullable=False)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="memberships")