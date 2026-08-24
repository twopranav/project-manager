from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.project import ProjectStatus
from app.models.project_member import ProjectRole

# Shared project input fields; name is required while description may be omitted.
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

# Input schema for creating a project; it inherits the fields defined by ProjectBase.
class ProjectCreate(ProjectBase):
    pass

# Output schema for a project; adds identity, ownership, status, and creation timestamp.
class ProjectOut(ProjectBase):
    id: str
    owner_id: str
    status: ProjectStatus
    created_at: datetime
    # Allow Pydantic to populate this output schema directly from ORM model attributes.
    class Config:
        from_attributes = True

# Input schema for adding a user to a project; the membership role defaults to contributor.
class ProjectMemberAdd(BaseModel):
    user_id: str
    project_role: ProjectRole = ProjectRole.contributor

# Output schema for a project membership; identifies the project, user, role, and join time.
class ProjectMemberOut(BaseModel):
    id: str
    project_id: str
    user_id: str
    project_role: ProjectRole
    joined_at: datetime
    # Allow Pydantic to populate this output schema directly from ORM model attributes.
    class Config:
        from_attributes = True

# Input schema for partial project updates; every field is optional so omitted fields can remain unchanged.
class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None

# Input schema for changing a project's membership role; the new role is required.
class ProjectMemberRoleUpdate(BaseModel):
    project_role: ProjectRole

# Output schema for aggregated project task statistics.
class ProjectStats(BaseModel):
    total_tasks: int
    tasks_by_status: dict[str, int]
    overdue_tasks: int