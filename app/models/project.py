import uuid, enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# Enum defining the three possible lifecycle states of a project.
class ProjectStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    completed = "completed"

# Table representing a project; each project has one owner and can contain members and tasks.
class Project(Base):
    __tablename__ = "projects"

    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Required human-readable project name; must be unique across all projects.
    name = Column(String, nullable=False, unique=True)
    # Optional longer project description.
    description = Column(Text)
    # Required foreign key identifying the user who owns the project.
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    # Required project lifecycle status, defaulting to active.
    status = Column(Enum(ProjectStatus), default=ProjectStatus.active, nullable=False)
    # Timestamp recording when the project was created.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # ORM relationship connecting the project to its owning User.
    owner = relationship("User", back_populates="owned_projects")
    # ORM relationship exposing the project's ProjectMember join-table records.
    members = relationship("ProjectMember", back_populates="project")
    # ORM relationship exposing all tasks belonging to this project.
    tasks = relationship("Task", back_populates="project")