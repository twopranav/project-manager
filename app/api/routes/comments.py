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

# Create the router that exposes comment endpoints under the /comments URL prefix.
router = APIRouter(prefix="/comments", tags=["comments"])


# Define a helper that retrieves a task or stops with a 404 response when it does not exist.
def _get_task_or_404(db: Session, task_id: str) -> Task:
# Look up the task by its identifier.
    task = db.query(Task).filter(Task.id == task_id).first()
# Check whether the task lookup returned no record.
    if not task:
# Return HTTP 404 when the reply would cross task boundaries.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
# Return the found task to the calling endpoint.
    return task


@router.post("/", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
# Handle comment creation for the authenticated project contributor.
def create_comment(
    comment_in: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Verify that the target task exists.
    task = _get_task_or_404(db, comment_in.task_id)
# Require viewer-level access to the project containing the task.
    require_project_role(db, current_user, task.project_id, ProjectRole.contributor)

# Validate the parent comment only when this comment is intended to be a reply.
    if comment_in.parent_comment_id:
# Look up the proposed parent comment.
        parent = db.query(Comment).filter(Comment.id == comment_in.parent_comment_id).first()
# Check whether the supplied parent comment exists.
        if not parent:
# Return HTTP 404 when the reply would cross task boundaries.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")
# Ensure the parent comment belongs to the same task as the new reply.
        if parent.task_id != comment_in.task_id:
# Return HTTP 400 when the reply would cross task boundaries.
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent comment belongs to a different task")

# Build the new comment record with its author, task, parent, and content.
    new_comment = Comment(
# Associate the comment with the target task.
        task_id=comment_in.task_id,
# Record the authenticated user as the comment author.
        user_id=current_user.id,
# Preserve the optional parent comment to form a reply relationship.
        parent_comment_id=comment_in.parent_comment_id,
# Store the submitted comment text.
        content=comment_in.content,
    )
# Stage the new comment for insertion.
    db.add(new_comment)
# Persist the deletion.
    db.commit()
# Reload the comment so generated database values are available.
    db.refresh(new_comment)
# Return the newly created comment.
    return new_comment


@router.get("/task/{task_id}", response_model=List[CommentTreeOut])
# Handle retrieval of all comments for a task.
def list_comments_for_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Verify that the target task exists.
    task = _get_task_or_404(db, task_id)
# Require viewer-level access to the project containing the task.
    require_project_role(db, current_user, task.project_id, ProjectRole.viewer)

# Query every comment for the task in creation order so the reply tree is deterministic.
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
# Create a response-schema node for every comment so replies can be attached manually.
    nodes = {
        c.id: CommentTreeOut(
            id=c.id,
# Associate the comment with the target task.
            task_id=c.task_id,
# Record the authenticated user as the comment author.
            user_id=c.user_id,
# Preserve the optional parent comment to form a reply relationship.
            parent_comment_id=c.parent_comment_id,
# Store the submitted comment text.
            content=c.content,
            created_at=c.created_at,
            updated_at=c.updated_at,
            replies=[],
        )
        for c in all_comments
    }
# Initialize the list that will contain only top-level comments.
    roots: List[CommentTreeOut] = []
# Walk through every comment once to connect it to its parent or the root list.
    for comment in all_comments:
# Retrieve the response node corresponding to the current ORM comment.
        node = nodes[comment.id]
# Check whether the current comment is a reply to another comment.
        if comment.parent_comment_id and comment.parent_comment_id in nodes:
# Attach the reply to its parent node.
            nodes[comment.parent_comment_id].replies.append(node)
# Treat comments without a valid parent as top-level comments.
        else:
# Add the top-level comment to the result tree.
            roots.append(node)

# Return the completed nested comment tree.
    return roots


@router.patch("/{comment_id}", response_model=CommentOut)
# Handle a comment edit request.
def edit_comment(
    comment_id: str,
    comment_update: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Look up the comment being deleted.
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
# Check whether the comment exists before deleting it.
    if not comment:
# Return HTTP 404 when the reply would cross task boundaries.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

# Calculate whether the authenticated user is the comment author.
    is_author = comment.user_id == current_user.id
# Calculate whether the authenticated user is the site-wide administrator.
    is_admin = current_user.global_role == GlobalRole.admin
# Allow deletion only to the author or site administrator.
    if not (is_author or is_admin):
# Return HTTP 400 when the reply would cross task boundaries.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own comments")

# Replace the stored comment content with the submitted content.
    comment.content = comment_update.content
# Persist the deletion.
    db.commit()
# Reload the edited comment from the database.
    db.refresh(comment)
# Return the updated comment.
    return comment


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
# Handle a comment deletion request.
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Look up the comment being deleted.
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
# Check whether the comment exists before deleting it.
    if not comment:
# Return HTTP 400 when the reply would cross task boundaries.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

# Calculate whether the authenticated user is the comment author.
    is_author = comment.user_id == current_user.id
# Calculate whether the authenticated user is the site-wide administrator.
    is_admin = current_user.global_role == GlobalRole.admin
# Allow deletion only to the author or site administrator.
    if not (is_author or is_admin):
# Return HTTP 400 when the reply would cross task boundaries.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own comments")

# Mark the comment for deletion from the database.
    db.delete(comment)
# Persist the deletion.
    db.commit()