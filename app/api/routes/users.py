from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    # get_current_user already did the DB lookup + JWT validation,
    # so there's nothing left to do here except hand back what we have
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