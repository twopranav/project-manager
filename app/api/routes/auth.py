from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User, GlobalRole
from app.schemas.user import UserCreate, UserOut
from app.schemas.token import Token
from app.core.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Every account registers as a plain member, no exceptions — including
    # the very first one. The global admin role is never granted through
    # this endpoint. It's assigned exactly once, manually, by running
    # app/scripts/bootstrap_admin.py directly against the database, and
    # after that only an existing admin can hand it to anyone else
    # (see PATCH /users/{id}/role).
    new_user = User(
        name=user_in.name,
        email=user_in.email,
        password_hash=hash_password(user_in.password),
        global_role=GlobalRole.member,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm calls the field "username" even though
    # we're using email as the login identifier — that's just the
    # standard OAuth2 field name, so we read it from form_data.username
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token)