from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.project_member import ProjectMember, ProjectRole
from app.models.task import Task, TaskStatus
from app.models.user import User, GlobalRole
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectOut, ProjectMemberAdd,
    ProjectMemberRoleUpdate, ProjectMemberOut, ProjectStats,
)
from app.api.deps import get_current_user, require_project_role

# Create the router that exposes project endpoints under the /projects URL prefix.
router = APIRouter(prefix="/projects", tags=["projects"])

# Define a guard that restricts project-admin role changes to a project admin or site admin.
def _require_admin_or_siteadmin(db: Session, current_user: User, project_id: str) -> None:
    """Gate for anything that grants/revokes the project-admin tier itself —
    prevents a manager from promoting themselves (or anyone) to admin."""
# Look up the caller’s membership in the target project.
    caller_membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    ).first()
# Calculate whether the caller is a project-level administrator.
    is_project_admin = caller_membership and caller_membership.project_role == ProjectRole.admin
# Calculate whether the caller is the site-wide administrator.
    is_site_admin = current_user.global_role == GlobalRole.admin
# Reject callers who are neither project admins nor site admins.
    if not (is_project_admin or is_site_admin):
# Return HTTP 404 when the caller is not a project member.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a project admin can grant, change, or remove the admin role",
        )

# Define a guard that prevents a project from losing its final administrator.
def _guard_last_admin(db: Session, project_id: str, user_id: str) -> None:
    """Raise if this change would leave the project with zero admins."""
# Count project admins other than the administrator being removed or demoted.
    other_admins = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.project_role == ProjectRole.admin,
        ProjectMember.user_id != user_id,
    ).count()
# Block the change when no other project administrator would remain.
    if other_admins == 0:
# Return HTTP 404 when the caller is not a project member.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This project must keep at least one admin",
        )

@router.post("/", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
# Handle creation of a project by the authenticated user.
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

# Reject project creation when the name is already used by another project & return 400
    if db.query(Project).filter(Project.name == project_in.name).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A project with this name already exists")
# Build the project record using the submitted details and current user as owner.
    new_project = Project(
# Store the submitted project name and description 
        name=project_in.name,
        description=project_in.description,
# Record the authenticated user as the project owner.
        owner_id=current_user.id,
    )
# Stage the new project for insertion.
    db.add(new_project)
# Persist the departure from the project.
    db.commit()
# Reload the project after insertion.
    db.refresh(new_project)

# Create the creator’s membership record in the new project.
    db.add(ProjectMember(
        project_id=new_project.id,
        user_id=current_user.id,
        project_role=ProjectRole.admin,  # creator becomes this project's admin
    ))
# Persist the departure from the project.
    db.commit()

    return new_project # Return the created project.



@router.get("/", response_model=List[ProjectOut])
# Handle project listing with optional status and pagination filters.
def list_my_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_: Optional[ProjectStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    # Only the site-wide (global) admin bypasses membership. A project-level
    # "manager" role only ever applies to projects they're actually a member
    # of — no global reach, per spec.
# Give the site-wide admin visibility across all projects.
    if current_user.global_role == GlobalRole.admin:
# Start an unrestricted project query for the site admin.
        query = db.query(Project)
    else:
# For normal users, start a query restricted to projects they own or belong to.
        query = (
# Select project records for the membership-scoped query.
            db.query(Project)
            .outerjoin(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(
                (Project.owner_id == current_user.id) | 
                (ProjectMember.user_id == current_user.id)
            )
        )
# Apply the status filter only when the caller supplied one.
    if status_ is not None:
# Restrict the project query to the requested status.
        query = query.filter(Project.status == status_)
# Sort newest projects first and apply offset/limit pagination.
    return query.order_by(Project.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{project_id}", response_model=ProjectOut)
# Handle retrieval of a single project.
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require viewer access and return the project allowed by the role guard.
    return require_project_role(db, current_user, project_id, ProjectRole.viewer)


@router.patch("/{project_id}", response_model=ProjectOut)
# Handle project updates for users with manager-level access.
def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require manager access and retrieve the target project.
    project = require_project_role(db, current_user, project_id, ProjectRole.manager)
# Convert only the fields actually supplied by the caller into a dictionary.
    update_data = project_update.model_dump(exclude_unset=True)
# Reject the rename when another project already uses the requested name & return 400
    if "name" in update_data and update_data["name"] != project.name:
        if db.query(Project).filter(Project.name == update_data["name"], Project.id != project_id).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A project with this name already exists")
# Apply each requested project-field change dynamically.
    for field, value in update_data.items():
# Assign the submitted value to the corresponding project attribute.
        setattr(project, field, value)

# Persist the departure from the project.
    db.commit()
# Reload and return the updated project.
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
# Handle project deletion for users with manager-level access.
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require viewer access before exposing project statistics.
    require_project_role(db, current_user, project_id, ProjectRole.manager)
# Check whether the project still contains any tasks.
    has_tasks = db.query(Task.id).filter(Task.project_id == project_id).first()
# Prevent deletion when tasks still depend on the project.
    if has_tasks:
# Return HTTP 400 when the caller is not a project member.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a project that still has tasks — delete its tasks first, or archive it via PATCH instead",
        )
# Remove all project-membership records associated with the project.
    db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete()
# Select project records for the membership-scoped query.
    db.query(Project).filter(Project.id == project_id).delete()
# Persist the departure from the project.
    db.commit()


@router.get("/{project_id}/members", response_model=List[ProjectMemberOut])
# Handle retrieval of the project membership list.
def list_project_members(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require viewer access before exposing project statistics.
    require_project_role(db, current_user, project_id, ProjectRole.viewer)
# Return all membership records belonging to the project.
    return db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=status.HTTP_201_CREATED)
# Handle adding a new project member.
def add_project_member(
    project_id: str,
    member_in: ProjectMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require viewer access before exposing project statistics.
    require_project_role(db, current_user, project_id, ProjectRole.manager)
# Apply the stronger admin-role guard when the new member is being made an admin.
    if member_in.project_role == ProjectRole.admin:
# Ensure the caller is authorized to alter the admin tier.
        _require_admin_or_siteadmin(db, current_user, project_id)
    target_user = db.query(User).filter(User.id == member_in.user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to add not found")
# Check whether the target user is already a member of this project.
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == member_in.user_id,
    ).first()
# Prevent duplicate project memberships.
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member of this project")
# Build the new project-membership record.
    new_member = ProjectMember(
        project_id=project_id,
        user_id=member_in.user_id,
        project_role=member_in.project_role,
    )
# Stage the membership for insertion.
    db.add(new_member)
# Persist the departure from the project.
    db.commit()
# Reload and return the membership with database-generated fields.
    db.refresh(new_member)
    return new_member


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberOut)
# Handle project updates for users with manager-level access.
def update_project_member_role(
    project_id: str,
    user_id: str,
    role_update: ProjectMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require viewer access before exposing project statistics.
    require_project_role(db, current_user, project_id, ProjectRole.manager)

# Look up the current user’s membership in the project.
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
# Check whether the current user is actually a member.
    if not membership:
# Return HTTP 404 when the caller is not a project member.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this project")

# Determine whether the requested change grants or removes project-admin status.
    touches_admin_tier = (
        role_update.project_role == ProjectRole.admin
        or membership.project_role == ProjectRole.admin
    )
# Apply the stronger authorization rule whenever the admin tier is involved.
    if touches_admin_tier:
# Ensure the caller is authorized to alter the admin tier.
        _require_admin_or_siteadmin(db, current_user, project_id)

# Protect the project when the departing user is an administrator.
    if membership.project_role == ProjectRole.admin and role_update.project_role != ProjectRole.admin:
# Prevent the user from leaving if they are the final project admin.
        _guard_last_admin(db, project_id, user_id)

# Store the requested project role on the membership.
    membership.project_role = role_update.project_role
# Persist the departure from the project.
    db.commit()
# Reload the membership after the database update.
    db.refresh(membership)
# Return the updated membership.
    return membership


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
# Handle manager-driven removal of a project member.
def remove_project_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require viewer access before exposing project statistics.
    require_project_role(db, current_user, project_id, ProjectRole.manager)

# Look up the current user’s membership in the project.
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
# Check whether the current user is actually a member.
    if not membership:
# Return HTTP 404 when the caller is not a project member.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this project")

# Protect the project when the departing user is an administrator.
    if membership.project_role == ProjectRole.admin:
# Ensure the caller is authorized to alter the admin tier.
        _require_admin_or_siteadmin(db, current_user, project_id)
# Prevent the user from leaving if they are the final project admin.
        _guard_last_admin(db, project_id, user_id)

# Mark the caller’s membership for deletion.
    db.delete(membership)
# Persist the departure from the project.
    db.commit()


@router.delete("/{project_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
# Handle self-service removal of the authenticated user from a project.
def leave_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Self-service: any member can remove themselves without needing
    manager+ (unlike the general remove_project_member endpoint)."""
# Look up the current user’s membership in the project.
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    ).first()
# Check whether the current user is actually a member.
    if not membership:
# Return HTTP 404 when the caller is not a project member.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You are not a member of this project")

# Protect the project when the departing user is an administrator.
    if membership.project_role == ProjectRole.admin:
# Prevent the user from leaving if they are the final project admin.
        _guard_last_admin(db, project_id, current_user.id)

# Mark the caller’s membership for deletion.
    db.delete(membership)
# Persist the departure from the project.
    db.commit()


@router.get("/{project_id}/stats", response_model=ProjectStats)
# Handle retrieval of a single project.
def get_project_stats(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Require viewer access before exposing project statistics.
    require_project_role(db, current_user, project_id, ProjectRole.viewer)

# Count tasks grouped by their current status.
    status_counts = (
        db.query(Task.status, func.count(Task.id))
        .filter(Task.project_id == project_id)
        .group_by(Task.status)
        .all()
    )
# Initialize every known task status with a zero count.
    tasks_by_status = {s.value: 0 for s in TaskStatus}
# Replace the zero for each status that actually has tasks.
    for task_status, count in status_counts:
# Store the database count under the status name used by the API.
        tasks_by_status[task_status.value] = count

# Calculate the total number of tasks across all statuses.
    total_tasks = sum(tasks_by_status.values())

# Count unfinished tasks whose due date is earlier than today.
    overdue_tasks = (
        db.query(func.count(Task.id))
        .filter(
            Task.project_id == project_id,
            Task.due_date < date.today(),
            Task.status != TaskStatus.done,
        )
        .scalar()
    )

# Package the aggregate counts into the project-statistics response schema.
    return ProjectStats(
        total_tasks=total_tasks,
        tasks_by_status=tasks_by_status,
        overdue_tasks=overdue_tasks,
    )