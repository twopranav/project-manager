from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class CommentCreate(BaseModel):
    task_id: str
    content: str
    parent_comment_id: Optional[str] = None

class CommentUpdate(BaseModel):
    content: str

class CommentOut(BaseModel):
    id: str
    task_id: str
    user_id: str
    parent_comment_id: Optional[str]
    content: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class CommentTreeOut(CommentOut):
    replies: List["CommentTreeOut"] = []

CommentTreeOut.model_rebuild()