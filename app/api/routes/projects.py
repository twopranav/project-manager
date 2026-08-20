from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectMemberAdd, ProjectMemberOut, ProjectStats
from app.api.deps import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])


def _ensure_project_member(db: Session, project_id: str, user_id: str):
    is_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
    if not is_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")


@router.post("/", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_project = Project(
        name=project_in.name,
        description=project_in.description,
        owner_id=current_user.id,
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    db.add(ProjectMember(
        project_id=new_project.id,
        user_id=current_user.id,
        project_role=ProjectRole.owner,
    ))
    db.commit()

    return new_project


@router.get("/", response_model=List[ProjectOut])
def list_my_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .filter(ProjectMember.user_id == current_user.id)
        .all()
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _ensure_project_member(db, project.id, current_user.id)
    return project


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: str,
    member_in: ProjectMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the project owner can add members")

    target_user = db.query(User).filter(User.id == member_in.user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to add not found")

    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == member_in.user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member of this project")

    new_member = ProjectMember(
        project_id=project_id,
        user_id=member_in.user_id,
        project_role=member_in.project_role,
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member


@router.get("/{project_id}/stats", response_model=ProjectStats)
def get_project_stats(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _ensure_project_member(db, project.id, current_user.id)

    status_counts = (
        db.query(Task.status, func.count(Task.id))
        .filter(Task.project_id == project_id)
        .group_by(Task.status)
        .all()
    )
    tasks_by_status = {s.value: 0 for s in TaskStatus}
    for task_status, count in status_counts:
        tasks_by_status[task_status.value] = count

    total_tasks = sum(tasks_by_status.values())

    overdue_tasks = (
        db.query(func.count(Task.id))
        .filter(
            Task.project_id == project_id,
            Task.due_date < date.today(),
            Task.status != TaskStatus.done,
        )
        .scalar()
    )

    return ProjectStats(
        total_tasks=total_tasks,
        tasks_by_status=tasks_by_status,
        overdue_tasks=overdue_tasks,
    )