import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# Join table connecting users to tasks while recording when each assignment was made.
class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    # Enforce at the database level that the same user cannot be assigned to the same task more than once.
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_user"),)
    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Required foreign key identifying the assigned task.
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    # Required foreign key identifying the assigned user.
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    # Timestamp recording when the assignment was created.
    assigned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # ORM relationship connecting this assignment to its Task.
    task = relationship("Task", back_populates="assignees")
    # ORM relationship connecting this assignment to its User.
    user = relationship("User")