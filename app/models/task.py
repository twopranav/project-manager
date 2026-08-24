import uuid, enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Date, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# Enum defining the possible lifecycle states of a task.
class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    in_review = "in_review"
    done = "done"
    blocked = "blocked"

# Enum defining the four possible task priority levels.
class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

# Table representing a task; each task belongs to one project and tracks its creator, assignees, comments, and status history.
class Task(Base):
    __tablename__ = "tasks"

    # Enforce that a task's title is unique within its own project (not globally).
    __table_args__ = (
        UniqueConstraint("project_id", "title", name="uq_task_project_title"),
    )

    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Required foreign key linking the task to its project.
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)

    # Required foreign key identifying the user who created the task.
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Required short title for the task.
    title = Column(String, nullable=False)

    # Optional longer task description.
    description = Column(Text)

    # Required task status, defaulting to todo.
    status = Column(Enum(TaskStatus), default=TaskStatus.todo, nullable=False)

    # Required task priority, defaulting to medium.
    priority = Column(Enum(TaskPriority), default=TaskPriority.medium, nullable=False)

    # Optional date by which the task should be completed.
    due_date = Column(Date)

    # Timestamp recording when the task was created.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Timestamp recording the last update, automatically refreshed whenever the task changes.
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # ORM relationship connecting the task to its containing Project.
    project = relationship("Project", back_populates="tasks")

    # ORM relationship connecting the task to the User who created it.
    creator = relationship("User", back_populates="created_tasks")

    # ORM relationship exposing the task's TaskAssignee join-table records.
    assignees = relationship("TaskAssignee", back_populates="task")

    # ORM relationship exposing all comments attached to this task.
    comments = relationship("Comment", back_populates="task")

    # ORM relationship exposing the task's chronological status-change records.
    status_history = relationship("TaskStatusHistory", back_populates="task")