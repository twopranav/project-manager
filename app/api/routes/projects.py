from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.task import Task, TaskStatus
from app.models.user import User, GlobalRole
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectOut, ProjectMemberAdd,
    ProjectMemberRoleUpdate, ProjectMemberOut, ProjectStats,
)
from app.api.deps import get_current_user, require_project_role

router = APIRouter(prefix="/projects", tags=["projects"])


def _require_admin_or_siteadmin(db: Session, current_user: User, project_id: str) -> None:
    """Gate for anything that grants/revokes the project-admin tier itself —
    prevents a manager from promoting themselves (or anyone) to admin."""
    caller_membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    ).first()
    is_project_admin = caller_membership and caller_membership.project_role == ProjectRole.admin
    is_site_admin = current_user.global_role == GlobalRole.admin
    if not (is_project_admin or is_site_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a project admin can grant, change, or remove the admin role",
        )


def _guard_last_admin(db: Session, project_id: str, user_id: str) -> None:
    """Raise if this change would leave the project with zero admins."""
    other_admins = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.project_role == ProjectRole.admin,
        ProjectMember.user_id != user_id,
    ).count()
    if other_admins == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This project must keep at least one admin",
        )


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
        project_role=ProjectRole.admin,  # creator becomes this project's admin
    ))
    db.commit()

    return new_project


@router.get("/", response_model=List[ProjectOut])
def list_my_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only the site-wide (global) admin bypasses membership. A project-level
    # "manager" role only ever applies to projects they're actually a member
    # of — no global reach, per spec.
    if current_user.global_role == GlobalRole.admin:
        return db.query(Project).all()

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
    return require_project_role(db, current_user, project_id, ProjectRole.viewer)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # manager+ gets full CRUD on projects they manage, per spec
    project = require_project_role(db, current_user, project_id, ProjectRole.manager)

    update_data = project_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_role(db, current_user, project_id, ProjectRole.manager)

    has_tasks = db.query(Task.id).filter(Task.project_id == project_id).first()
    if has_tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a project that still has tasks — delete its tasks first, or archive it via PATCH instead",
        )

    db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete()
    db.query(Project).filter(Project.id == project_id).delete()
    db.commit()


@router.get("/{project_id}/members", response_model=List[ProjectMemberOut])
def list_project_members(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_role(db, current_user, project_id, ProjectRole.viewer)
    return db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: str,
    member_in: ProjectMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_role(db, current_user, project_id, ProjectRole.manager)

    if member_in.project_role == ProjectRole.admin:
        _require_admin_or_siteadmin(db, current_user, project_id)

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


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberOut)
def update_project_member_role(
    project_id: str,
    user_id: str,
    role_update: ProjectMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_role(db, current_user, project_id, ProjectRole.manager)

    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this project")

    touches_admin_tier = (
        role_update.project_role == ProjectRole.admin
        or membership.project_role == ProjectRole.admin
    )
    if touches_admin_tier:
        _require_admin_or_siteadmin(db, current_user, project_id)

    if membership.project_role == ProjectRole.admin and role_update.project_role != ProjectRole.admin:
        _guard_last_admin(db, project_id, user_id)

    membership.project_role = role_update.project_role
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_role(db, current_user, project_id, ProjectRole.manager)

    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this project")

    if membership.project_role == ProjectRole.admin:
        _require_admin_or_siteadmin(db, current_user, project_id)
        _guard_last_admin(db, project_id, user_id)

    db.delete(membership)
    db.commit()


@router.get("/{project_id}/stats", response_model=ProjectStats)
def get_project_stats(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_role(db, current_user, project_id, ProjectRole.viewer)

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