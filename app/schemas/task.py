from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional
from app.models.task import TaskStatus, TaskPriority

# Shared task input fields; title is required, priority defaults to medium, and description/due_date are optional.
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.medium
    due_date: Optional[date] = None

# Input schema for creating a task; adds the required project identifier to TaskBase.
class TaskCreate(TaskBase):
    project_id: str

# Input schema for partial task updates; all fields are optional so only supplied fields need to change.
class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None

# Output schema for a task; includes identity, project, creator, current status, and timestamps.
class TaskOut(TaskBase):
    id: str
    project_id: str
    created_by: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    # Allow Pydantic to populate this output schema directly from ORM model attributes.
    class Config:
        from_attributes = True


# Output schema representing one task-status transition, including previous and new status.
class TaskStatusHistoryOut(BaseModel):
    id: str
    task_id: str
    changed_by: str
    old_status: Optional[TaskStatus]
    new_status: TaskStatus
    changed_at: datetime
    # Allow Pydantic to populate this output schema directly from ORM model attributes.
    class Config:
        from_attributes = True