from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional
from app.models.task import TaskStatus, TaskPriority

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.medium
    due_date: Optional[date] = None

class TaskCreate(TaskBase):
    project_id: str

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None

class TaskOut(TaskBase):
    id: str
    project_id: str
    created_by: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True