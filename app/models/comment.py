import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# Table for task comments; each comment belongs to one task and one user, and can optionally reply to another comment.
class Comment(Base):
    __tablename__ = "comments"
    # Primary key generated as a UUID string.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Required foreign key linking this comment to the task it belongs to.
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    # Required foreign key identifying the user who wrote the comment.
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    # Optional self-referencing foreign key that makes this comment a reply to another comment.
    parent_comment_id = Column(String(36), ForeignKey("comments.id"), nullable=True)
    # Required text containing the actual comment content.
    content = Column(Text, nullable=False)
    # Timestamp recording when the comment was created.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Timestamp recording the last update, automatically refreshed whenever the comment changes.
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # ORM relationship allowing the comment to access its associated task.
    task = relationship("Task", back_populates="comments")
    # ORM relationship allowing the comment to access the User who authored it.
    author = relationship("User", back_populates="comments")
    # Self-referencing ORM relationship allowing a comment to contain its replies.
    replies = relationship("Comment", backref="parent", remote_side=[id])