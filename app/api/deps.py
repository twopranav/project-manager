from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.config import get_settings
from app.models.user import User, GlobalRole
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


# Project-role hierarchy, low to high. Determines who outranks whom within
# a single project's membership.
_ROLE_RANK = {
    ProjectRole.viewer: 0,
    ProjectRole.contributor: 1,
    ProjectRole.manager: 2,
    ProjectRole.owner: 3,
}


def require_project_role(
    db: Session,
    current_user: User,
    project_id: str,
    min_role: ProjectRole = ProjectRole.viewer,
) -> Project:
    """
    Single source of truth for "can this user act on this project".

    - A site-wide admin (User.global_role == admin) bypasses membership
      entirely and can act on ANY project, member or not. This is the
      "owner can do anything to any project" tier — it lives on the User,
      not on a per-project ProjectMember row, because a ProjectMember row
      is inherently scoped to one project and can't represent cross-project
      power.
    - Everyone else must hold a ProjectMember row for this exact project,
      with a project_role at least as senior as min_role.

    Returns the Project (so callers that already need it don't re-query).
    Raises 404 if the project doesn't exist, 403 if access is insufficient.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if current_user.global_role == GlobalRole.admin:
        return project

    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")

    if _ROLE_RANK[membership.project_role] < _ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires '{min_role.value}' role or higher in this project",
        )

    return project