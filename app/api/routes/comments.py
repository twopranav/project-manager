from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.comment import Comment
from app.models.task import Task
from app.models.project_member import ProjectRole
from app.models.user import User, GlobalRole
from app.schemas.comment import CommentCreate, CommentUpdate, CommentOut, CommentTreeOut
from app.api.deps import get_current_user, require_project_role

router = APIRouter(prefix="/comments", tags=["comments"])


def _get_task_or_404(db: Session, task_id: str) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("/", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def create_comment(
    comment_in: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_404(db, comment_in.task_id)
    require_project_role(db, current_user, task.project_id, ProjectRole.contributor)

    if comment_in.parent_comment_id:
        parent = db.query(Comment).filter(Comment.id == comment_in.parent_comment_id).first()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")
        if parent.task_id != comment_in.task_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent comment belongs to a different task")

    new_comment = Comment(
        task_id=comment_in.task_id,
        user_id=current_user.id,
        parent_comment_id=comment_in.parent_comment_id,
        content=comment_in.content,
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment


@router.get("/task/{task_id}", response_model=List[CommentTreeOut])
def list_comments_for_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_404(db, task_id)
    require_project_role(db, current_user, task.project_id, ProjectRole.viewer)

    all_comments = (
        db.query(Comment).filter(Comment.task_id == task_id).order_by(Comment.created_at).all()
    )

    # Build the reply tree in one pass: wrap each ORM row, then attach
    # each comment under its parent's "replies" list. Top-level comments
    # (parent_comment_id is None) are what we hand back.
    # Build manually rather than CommentTreeOut.model_validate(c): the ORM
    # Comment model already has its own "replies" backref (self-referential
    # relationship), which would collide with and override our tree's
    # "replies" list if we let from_attributes pull it in directly.
    nodes = {
        c.id: CommentTreeOut(
            id=c.id,
            task_id=c.task_id,
            user_id=c.user_id,
            parent_comment_id=c.parent_comment_id,
            content=c.content,
            created_at=c.created_at,
            updated_at=c.updated_at,
            replies=[],
        )
        for c in all_comments
    }
    roots: List[CommentTreeOut] = []
    for comment in all_comments:
        node = nodes[comment.id]
        if comment.parent_comment_id and comment.parent_comment_id in nodes:
            nodes[comment.parent_comment_id].replies.append(node)
        else:
            roots.append(node)

    return roots


@router.patch("/{comment_id}", response_model=CommentOut)
def edit_comment(
    comment_id: str,
    comment_update: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    is_author = comment.user_id == current_user.id
    is_admin = current_user.global_role == GlobalRole.admin
    if not (is_author or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own comments")

    comment.content = comment_update.content
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    is_author = comment.user_id == current_user.id
    is_admin = current_user.global_role == GlobalRole.admin
    if not (is_author or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own comments")

    db.delete(comment)
    db.commit()