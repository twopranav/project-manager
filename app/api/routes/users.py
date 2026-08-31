from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User, GlobalRole
from app.schemas.user import UserOut, UserUpdate, UserGlobalRoleUpdate
from app.api.deps import get_current_user
from app.core.security import hash_password
from app.core.security_alerts import log_unauthorized_role_change, log_access_denied_and_check_repeated
from app.models.project_member import ProjectMember, ProjectRole

# Create the router that exposes user endpoints under the /users URL prefix.
router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserOut)
# Handle retrieval of the current user profile.
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    # get_current_user already did the DB lookup + JWT validation,
    # so there's nothing left to do here except hand back what we have
# Return the updated profile.
    return current_user


@router.patch("/me", response_model=UserOut)
# Handle self-service profile updates.
def update_my_profile(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Extract only the profile fields actually supplied by the caller.
    update_data = user_update.model_dump(exclude_unset=True)

# Update the name only when a non-empty name was submitted.
    if "name" in update_data and update_data["name"]:
# Store the new display name on the current user.
        current_user.name = update_data["name"]

# Update the password only when a non-empty password was submitted.
    if "password" in update_data and update_data["password"]:
# Hash and store the replacement password securely.
        current_user.password_hash = hash_password(update_data["password"])

# Persist the global-role change.
    db.commit()
# Reload the user after saving the changes.
    db.refresh(current_user)
# Return the updated profile.
    return current_user


@router.get("/lookup", response_model=UserOut)
# Handle email-based user lookup for project-member workflows.
def lookup_user_by_email(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only site admins, or anyone holding manager/admin rank in at least one
    # project — may search by email. Plain contributors/viewers get 403.
    # This is a global capacity check (not scoped to one project), since
    # at lookup time there's no target project to scope it to yet.
    is_site_admin = current_user.global_role == GlobalRole.admin
    has_manager_somewhere = db.query(ProjectMember).filter(
        ProjectMember.user_id == current_user.id,
        ProjectMember.project_role == ProjectRole.manager,
    ).first() is not None

    if not (is_site_admin or has_manager_somewhere):
        log_access_denied_and_check_repeated(db, current_user, "not a manager/admin anywhere (user lookup)")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only project managers or site admins can look up users",
        )

    # Search for the user whose email matches the supplied value.
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}/role", response_model=UserOut)
# Handle global-role changes initiated by the current site administrator.
def update_user_global_role(
    user_id: str,
    role_update: UserGlobalRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Site-wide role changes are a site-admin-only action. There is no
    # "promote yourself" path — the admin is set once via the bootstrap
    # script (app/scripts/bootstrap_admin.py) and can only be reassigned
    # by the current admin. Anyone else who tries gets a 403 and the
    # attempt is logged for the real admin to see.
# Reject anyone who is not the site-wide administrator.
    if current_user.global_role != GlobalRole.admin:
# Record an unauthorized role-change attempt for later security review.
        log_unauthorized_role_change(
            db=db,
            actor=current_user,
            target_user_id=user_id,
            attempted_role=role_update.global_role.value,
        )
# Return HTTP 400 until another administrator has been promoted.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the site admin can change a user's global role",
        )

# Granting admin is only allowed through the dedicated transfer flow, which
# demotes the current admin and promotes the target in one transaction —
# this endpoint has no such safeguard and would just hit the DB constraint.
    if role_update.global_role == GlobalRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /admin/transfer-admin to transfer admin rights.",
        )

# Find the user whose global role is being changed.
    target_user = db.query(User).filter(User.id == user_id).first()
# Check whether the target account exists.
    if not target_user:
# Return HTTP 400 until another administrator has been promoted.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

# Detect when the current admin is attempting to change their own role.
    if target_user.id == current_user.id:
# Search for another site administrator who could preserve administrative access.
        other_admins = (
            db.query(User.id)
            .filter(User.global_role == GlobalRole.admin, User.id != current_user.id)
            .first()
        )
# Prevent the current admin from removing the final site-admin account.
        if other_admins is None:
# Return HTTP 400 until another administrator has been promoted.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="There must be at least one site admin — promote someone else first",
            )

# Apply the requested site-wide role to the target user.
    target_user.global_role = role_update.global_role
# Persist the global-role change.
    db.commit()
# Reload the target user after the role update.
    db.refresh(target_user)
# Return the user with the updated global role.
    return target_user