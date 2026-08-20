from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User, GlobalRole
from app.schemas.user import UserOut, UserUpdate, UserGlobalRoleUpdate
from app.api.deps import get_current_user
from app.core.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    # get_current_user already did the DB lookup + JWT validation,
    # so there's nothing left to do here except hand back what we have
    return current_user


@router.patch("/me", response_model=UserOut)
def update_my_profile(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    update_data = user_update.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"]:
        current_user.name = update_data["name"]

    if "password" in update_data and update_data["password"]:
        current_user.password_hash = hash_password(update_data["password"])

    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/lookup", response_model=UserOut)
def lookup_user_by_email(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # needed so a project owner can find someone's id before adding
    # them as a member — you can't require shared-project membership
    # here, since that's exactly what this lookup is a prerequisite for
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}/role", response_model=UserOut)
def update_user_global_role(
    user_id: str,
    role_update: UserGlobalRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Site-wide role changes are a site-admin-only action — this is the
    # promotion path once the bootstrap (first-user-is-admin) account exists.
    if current_user.global_role != GlobalRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a site admin can change a user's global role",
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target_user.id == current_user.id and role_update.global_role != GlobalRole.admin:
        other_admins = (
            db.query(User.id)
            .filter(User.global_role == GlobalRole.admin, User.id != current_user.id)
            .first()
        )
        if other_admins is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="There must be at least one site admin — promote someone else first",
            )

    target_user.global_role = role_update.global_role
    db.commit()
    db.refresh(target_user)
    return target_user