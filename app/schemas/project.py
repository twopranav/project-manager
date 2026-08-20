from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.project import ProjectStatus

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectOut(ProjectBase):
    id: str
    owner_id: str
    status: ProjectStatus
    created_at: datetime
    class Config:
        from_attributes = True