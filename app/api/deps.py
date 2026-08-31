from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.config import get_settings
from app.models.user import User, GlobalRole
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.core.security_alerts import log_access_denied_and_check_repeated

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Runs on every protected route via Depends(). Decodes the bearer JWT, pulls
# the user id out of it, and loads that User fresh from the DB every request
# (so a role change takes effect immediately, no stale-token permissions).
# Any failure — bad signature, expired, missing "sub", user no longer exists — is a 401.
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
}


# THE permission gate — nearly every project/task/member route calls this.
# Site admin bypasses membership entirely; everyone else needs a ProjectMember
# row for this exact project ranked >= min_role. 404 = no such project, 403 = not senior enough.
def require_project_role(
    db: Session,
    current_user: User,
    project_id: str,
    min_role: ProjectRole = ProjectRole.viewer,
) -> Project:
    # Step 1: project must exist at all.
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    # Step 2: site-wide admin skips membership checks entirely — full access to any project.
    if current_user.global_role == GlobalRole.admin:
        return project
    # Step 3: everyone else must have a ProjectMember row for THIS project.
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    ).first()
    if not membership:
        log_access_denied_and_check_repeated(db, current_user, f"not a member of project {project_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")
    # Step 4: their project_role rank must meet or exceed what the caller required.
    if _ROLE_RANK[membership.project_role] < _ROLE_RANK[min_role]:
        log_access_denied_and_check_repeated(
            db, current_user, f"role '{membership.project_role.value}' below required '{min_role.value}' on project {project_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires '{min_role.value}' role or higher in this project",
        )
    return project