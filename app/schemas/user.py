from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from app.models.user import GlobalRole

# Shared user input fields; email must pass Pydantic's EmailStr validation.
class UserBase(BaseModel):
    name: str
    email: EmailStr

# Input schema for registration; adds the required password before the API hashes it.
class UserCreate(UserBase):
    password: str

# Output schema for a user; exposes identity, email, global role, and creation time but not the password.
class UserOut(UserBase):
    id: str
    global_role: GlobalRole
    created_at: datetime
    # Allow Pydantic to populate this output schema directly from ORM model attributes.
    class Config:
        from_attributes = True


# Input schema for partial self-profile updates; both name and password are optional.
class UserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None


# Input schema for changing a user's global role; the requested GlobalRole is required.
class UserGlobalRoleUpdate(BaseModel):
    global_role: GlobalRole