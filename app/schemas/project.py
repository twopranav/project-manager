from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.project import ProjectStatus
from app.models.project_member import ProjectRole

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

class ProjectMemberAdd(BaseModel):
    user_id: str
    project_role: ProjectRole = ProjectRole.contributor

class ProjectMemberOut(BaseModel):
    id: str
    project_id: str
    user_id: str
    project_role: ProjectRole
    joined_at: datetime
    class Config:
        from_attributes = True