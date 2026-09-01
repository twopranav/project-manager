import uuid, enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from app.models.task import TaskStatus

# Table recording every status transition made to a task.
class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"
    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Required foreign key identifying the task whose status changed.
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    # Required foreign key identifying the user who performed the status change.
    changed_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    # Previous task status, nullable because a newly created task has no previous status.
    old_status = Column(Enum(TaskStatus), nullable=True)
    # Required new status resulting from the transition.
    new_status = Column(Enum(TaskStatus), nullable=False)
    # Timestamp recording when the status transition occurred.
    changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # ORM relationship connecting this history record to its Task.
    task = relationship("Task", back_populates="status_history")