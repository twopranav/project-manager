import uuid, enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class GlobalRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    member = "member"

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    global_role = Column(Enum(GlobalRole), default=GlobalRole.member, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owned_projects = relationship("Project", back_populates="owner")
    memberships = relationship("ProjectMember", back_populates="user")
    created_tasks = relationship("Task", back_populates="creator")
    comments = relationship("Comment", back_populates="author")