from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User, GlobalRole
from app.schemas.user import UserCreate, UserOut
from app.schemas.token import Token
from app.core.security import hash_password, verify_password, create_access_token

# Create the router that exposes authentication endpoints under the /auth URL prefix.
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
# Handle registration using the submitted user data and database session.
def register(user_in: UserCreate, db: Session = Depends(get_db)):
# Check whether an account with the submitted email already exists.
    existing = db.query(User).filter(User.email == user_in.email).first()
# Prevent duplicate accounts when the email is already registered.
    if existing:
# Return HTTP 401 without revealing which credential was wrong.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Every account registers as a plain member, no exceptions — including
    # the very first one. The global admin role is never granted through
    # this endpoint. It's assigned exactly once, manually, by running
    # app/scripts/bootstrap_admin.py directly against the database, and
    # after that only an existing admin can hand it to anyone else
    # (see PATCH /users/{id}/role).
# Build the new user record and explicitly assign the normal member role.
    new_user = User(
# Copy the submitted display name into the new user record.
        name=user_in.name,
# Copy the submitted email into the new user record.
        email=user_in.email,
# Hash the submitted password before storing it in the database.
        password_hash=hash_password(user_in.password),
# Ensure self-registration can only create a normal member account.
        global_role=GlobalRole.member,
    )
# Stage the new user record for insertion into the database.
    db.add(new_user)
# Persist the new account to the database.
    db.commit()
# Reload the user so generated database fields are available.
    db.refresh(new_user)
# Return the newly created user through the response schema.
    return new_user

@router.post("/login", response_model=Token)
# Handle login using the standard OAuth2 username/password form and database session.
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm calls the field "username" even though
    # we're using email as the login identifier — that's just the
    # standard OAuth2 field name, so we read it from form_data.username
# Find the account whose email matches the OAuth2 form username field.
    user = db.query(User).filter(User.email == form_data.username).first()
# Reject the login when the account does not exist or the supplied password is incorrect.
    if not user or not verify_password(form_data.password, user.password_hash):
# Return HTTP 401 without revealing which credential was wrong.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

# Create a signed access token whose subject identifies the authenticated user.
    access_token = create_access_token(subject=user.id)
# Return the access token in the API token response format.
    return Token(access_token=access_token)