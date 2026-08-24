from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

# Input schema for creating a comment; requires a task and content, with an optional parent comment for replies.
class CommentCreate(BaseModel):
    task_id: str
    content: str
    parent_comment_id: Optional[str] = None

# Input schema for editing a comment; only the replacement content is accepted.
class CommentUpdate(BaseModel):
    content: str

# Output schema for a single comment; includes its task, author, optional parent, content, and timestamps.
class CommentOut(BaseModel):
    id: str
    task_id: str
    user_id: str
    parent_comment_id: Optional[str]
    content: str
    created_at: datetime
    updated_at: datetime
    # Allow Pydantic to populate this output schema directly from ORM model attributes.
    class Config:
        from_attributes = True

# Output schema extending CommentOut with recursively nested replies for building a comment tree.
class CommentTreeOut(CommentOut):
    replies: List["CommentTreeOut"] = []

# Rebuild the recursive schema so CommentTreeOut can refer to itself.
CommentTreeOut.model_rebuild()