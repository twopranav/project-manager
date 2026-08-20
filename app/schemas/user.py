from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.models.user import GlobalRole

class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    id: str
    global_role: GlobalRole
    created_at: datetime
    class Config:
        from_attributes = True