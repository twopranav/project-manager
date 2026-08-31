from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.task_assignee import TaskAssignee
from app.models.task_status_history import TaskStatusHistory
from app.models.comment import Comment
from app.models.project_member import ProjectRole, ProjectMember
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut, TaskStatusHistoryOut
from app.api.deps import get_current_user, require_project_role

# Create the router that exposes task endpoints under the /tasks URL prefix.
router = APIRouter(prefix="/tasks", tags=["tasks"])

# Fields a contributor (basic perms) may touch via PATCH — status only.
# Anything else (title/description/priority/due_date) needs manager+.
# Define the only task field that a contributor may change without manager-level access.
_contributor_EDITABLE_FIELDS = {"status"}


# Define a helper that retrieves a task or raises a 404 when it does not exist.
def _get_task_or_404(db: Session, task_id: str) -> Task:
# Look up the task by its identifier.
    task = db.query(Task).filter(Task.id == task_id).first()
# Check whether the task lookup returned no task.
    if not task:
# Return HTTP 404 when the assignment cannot be found.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
# Return the updated task.
    return task


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
# Handle task creation for a project manager.
def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require manager-level access to create tasks.
    require_project_role(db, current_user, task_in.project_id, ProjectRole.manager)

# Reject task creation when the title is already used within this project & return 400
    if db.query(Task).filter(Task.project_id == task_in.project_id, Task.title == task_in.title).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A task with this title already exists in this project")

# Build the task record from the submitted task details.
    new_task = Task(
# Associate the task with the selected project.
        project_id=task_in.project_id,
# Record the authenticated user as the task creator.
        created_by=current_user.id,
# Store the submitted task title.
        title=task_in.title,
# Store the submitted task description.
        description=task_in.description,
# Store the submitted task priority.
        priority=task_in.priority,
# Store the submitted task due date.
        due_date=task_in.due_date,
    )
# Stage the new task for insertion.
    db.add(new_task)
# Persist the new status-history entry.
    db.commit()
# Reload the task after insertion.
    db.refresh(new_task)

# Create a status-history record describing the transition.
    db.add(TaskStatusHistory(
# Link the history entry to the newly created task.
        task_id=new_task.id,
# Record who created the initial status state.
        changed_by=current_user.id,
# Record that there was no previous status because the task is new.
        old_status=None,
# Record the task’s initial status in the history.
        new_status=new_task.status,
    ))
# Persist the new status-history entry.
    db.commit()

# Return the newly created task.
    return new_task


@router.get("/project/{project_id}", response_model=List[TaskOut])
# Handle project task listing with optional filters and pagination.
def list_tasks_for_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_: Optional[TaskStatus] = Query(default=None, alias="status"),
    priority: Optional[TaskPriority] = Query(default=None),
    assignee_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
# Require viewer-level access to list tasks.
    require_project_role(db, current_user, project_id, ProjectRole.viewer)

# Start a task query scoped to the requested project.
    query = db.query(Task).filter(Task.project_id == project_id)
# Apply a status filter only when the caller supplied one.
    if status_ is not None:
# Restrict results to tasks with the requested priority.
        query = query.filter(Task.status == status_)
# Apply a priority filter only when one was supplied.
    if priority is not None:
# Restrict results to tasks with the requested priority.
        query = query.filter(Task.priority == priority)
# Apply an assignee filter only when one was supplied.
    if assignee_id is not None:
# Join the assignment table and keep only tasks assigned to the requested user.
        query = query.join(TaskAssignee, TaskAssignee.task_id == Task.id).filter(
            TaskAssignee.user_id == assignee_id
        )

# Return status-history records ordered from earliest to latest change.
    return (
        query.order_by(Task.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/assigned/me", response_model=List[TaskOut])
# Handle retrieval of the caller’s assigned tasks.
def list_my_assigned_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # must stay registered above /{task_id} or "assigned" gets swallowed as a task_id
# Return status-history records ordered from earliest to latest change.
    return (
        db.query(Task)
        .join(TaskAssignee, TaskAssignee.task_id == Task.id)
        .filter(TaskAssignee.user_id == current_user.id)
        .all()
    )


@router.get("/{task_id}", response_model=TaskOut)
# Handle retrieval of a single task.
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Retrieve the task before changing its assignments.
    task = _get_task_or_404(db, task_id)
# Require viewer-level access to view a task.
    require_project_role(db, current_user, task.project_id, ProjectRole.viewer)
# Return the updated task.
    return task


@router.get("/{task_id}/history", response_model=List[TaskStatusHistoryOut])
# Handle retrieval of a single task.
def get_task_status_history(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Retrieve the task before changing its assignments.
    task = _get_task_or_404(db, task_id)
# Require viewer-level access to view a task's history.
    require_project_role(db, current_user, task.project_id, ProjectRole.viewer)
# Return status-history records ordered from earliest to latest change.
    return (
# Remove status-history records associated with the task.
        db.query(TaskStatusHistory)
        .filter(TaskStatusHistory.task_id == task_id)
        .order_by(TaskStatusHistory.changed_at)
        .all()
    )


@router.patch("/{task_id}", response_model=TaskOut)
# Handle task updates with role requirements based on which fields change.
def update_task(
    task_id: str,
    task_update: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Retrieve the task before changing its assignments.
    task = _get_task_or_404(db, task_id)
# Extract only fields actually supplied in the update request.
    update_data = task_update.model_dump(exclude_unset=True)
# Calculate the set of task fields the caller is attempting to modify.
    fields_being_changed = set(update_data.keys())
# Allow contributor-level access when every changed field is status-only.
    if fields_being_changed <= _contributor_EDITABLE_FIELDS:
# Set the minimum required role to manager for title, description, priority, or due-date changes.
        min_role = ProjectRole.contributor
# Require stronger permissions when any protected task field is being changed.
    else:
# Set the minimum required role to manager for title, description, priority, or due-date changes.
        min_role = ProjectRole.manager  # touching title/description/priority/due_date
# Require the role determined above to update the task.
    require_project_role(db, current_user, task.project_id, min_role)

# Reject the rename when another task in the same project already uses the requested title & return 400
    if "title" in update_data and update_data["title"] != task.title:
        if db.query(Task).filter(Task.project_id == task.project_id, Task.title == update_data["title"], Task.id != task_id).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A task with this title already exists in this project")

# Preserve the task’s previous status so a status transition can be recorded later.
    old_status = task.status
# Apply every requested task-field update.
    for field, value in update_data.items():
# Assign the submitted value to the corresponding task attribute.
        setattr(task, field, value)
# Persist the new status-history entry.
    db.commit()
# Reload the updated task from the database.
    db.refresh(task)

# Record history only when the request included a status change and the value actually changed.
    if "status" in update_data and update_data["status"] != old_status:
# Create a status-history record describing the transition.
        db.add(TaskStatusHistory(
# Link the history entry to the newly created task.
            task_id=task.id,
# Record who created the initial status state.
            changed_by=current_user.id,
            old_status=old_status,
# Record the task’s initial status in the history.
            new_status=task.status,
        ))
# Persist the new status-history entry.
        db.commit()
# Return the updated task.
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
# Handle deletion of a task for a project manager.
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Retrieve the task before changing its assignments.
    task = _get_task_or_404(db, task_id)
# Require manager-level access to delete a task.
    require_project_role(db, current_user, task.project_id, ProjectRole.manager)
# Remove comments associated with the task first.
    db.query(Comment).filter(Comment.task_id == task_id).delete()
# Remove task-assignment records associated with the task.
    db.query(TaskAssignee).filter(TaskAssignee.task_id == task_id).delete()
# Remove status-history records associated with the task.
    db.query(TaskStatusHistory).filter(TaskStatusHistory.task_id == task_id).delete()
# Mark the task itself for deletion.
    db.delete(task)
# Persist the new status-history entry.
    db.commit()


@router.post("/{task_id}/assign", status_code=status.HTTP_201_CREATED)
# Handle assignment of a user to a task.
def assign_user_to_task(
    task_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Retrieve the task before changing its assignments.
    task = _get_task_or_404(db, task_id)
# Require manager-level access to manage task assignments.
    require_project_role(db, current_user, task.project_id, ProjectRole.manager)
# Check that the target user is a member of the task’s project.
    assignee_is_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == task.project_id,
        ProjectMember.user_id == user_id,
    ).first()
# Reject assignments to users outside the project.
    if not assignee_is_member:
# Return HTTP 400 when the assignment cannot be found.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User being assigned is not a member of this project")
# Check whether the target user is already assigned to the task.
    existing = db.query(TaskAssignee).filter(
        TaskAssignee.task_id == task_id,
        TaskAssignee.user_id == user_id,
    ).first()
# Prevent duplicate task assignments.
    if existing:
# Return HTTP 400 when the assignment cannot be found.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already assigned to this task")
# Create the task-assignment record.
    db.add(TaskAssignee(task_id=task_id, user_id=user_id))
# Persist the new status-history entry.
    db.commit()
# Return a simple success message after assignment.
    return {"detail": "User assigned"}

@router.delete("/{task_id}/assign/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
# Handle removal of a user from a task.
def unassign_user_from_task(
    task_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Retrieve the task before changing its assignments.
    task = _get_task_or_404(db, task_id)
# Require manager-level access to manage task assignments.
    require_project_role(db, current_user, task.project_id, ProjectRole.manager)

# Look up the specific task-assignment record.
    assignment = db.query(TaskAssignee).filter(
        TaskAssignee.task_id == task_id,
        TaskAssignee.user_id == user_id,
    ).first()
# Check whether the requested assignment exists.
    if not assignment:
# Return HTTP 404 when the assignment cannot be found.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

# Mark the assignment for deletion.
    db.delete(assignment)
# Persist the new status-history entry.
    db.commit()