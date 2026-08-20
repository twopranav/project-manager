from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.task import Task
from app.models.task_assignee import TaskAssignee
from app.models.task_status_history import TaskStatusHistory
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _ensure_project_member(db: Session, project_id: str, user_id: str):
    is_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
    if not is_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_project_member(db, task_in.project_id, current_user.id)

    new_task = Task(
        project_id=task_in.project_id,
        created_by=current_user.id,
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority,
        due_date=task_in.due_date,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    # log the initial status too, so history is complete from creation
    db.add(TaskStatusHistory(
        task_id=new_task.id,
        changed_by=current_user.id,
        old_status=None,
        new_status=new_task.status,
    ))
    db.commit()

    return new_task


@router.get("/project/{project_id}", response_model=List[TaskOut])
def list_tasks_for_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_project_member(db, project_id, current_user.id)
    return db.query(Task).filter(Task.project_id == project_id).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    _ensure_project_member(db, task.project_id, current_user.id)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    task_update: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    _ensure_project_member(db, task.project_id, current_user.id)

    update_data = task_update.model_dump(exclude_unset=True)
    old_status = task.status

    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    # only log history if status actually changed
    if "status" in update_data and update_data["status"] != old_status:
        db.add(TaskStatusHistory(
            task_id=task.id,
            changed_by=current_user.id,
            old_status=old_status,
            new_status=task.status,
        ))
        db.commit()

    return task


@router.post("/{task_id}/assign", status_code=status.HTTP_201_CREATED)
def assign_user_to_task(
    task_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_project_member(db, task.project_id, current_user.id)   # caller must be a member
    _ensure_project_member(db, task.project_id, user_id)           # assignee must be a member too

    existing = db.query(TaskAssignee).filter(
        TaskAssignee.task_id == task_id,
        TaskAssignee.user_id == user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already assigned to this task")

    db.add(TaskAssignee(task_id=task_id, user_id=user_id))
    db.commit()
    return {"detail": "User assigned"}


@router.delete("/{task_id}/assign/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_user_from_task(
    task_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    _ensure_project_member(db, task.project_id, current_user.id)

    assignment = db.query(TaskAssignee).filter(
        TaskAssignee.task_id == task_id,
        TaskAssignee.user_id == user_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    db.delete(assignment)
    db.commit()