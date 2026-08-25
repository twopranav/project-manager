"""
Creates the first global admin account directly in the database.

Why this exists: /auth/register always creates a `member` (see auth.py),
so there is no API path that can create an admin. That's intentional -
it stops anyone from self-elevating to admin over the API. This script
is the one-time, out-of-band way to seed that first admin.

Usage:
    python -m app.scripts.bootstrap_admin
"""

import sys

from app.db.session import SessionLocal
from app.models.user import User, GlobalRole
from app.core.security import hash_password

# Placeholders to be edited
ADMIN_NAME = "Admin"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "changeme123"

def create_first_admin():
    # Open a database session (same SessionLocal the app uses).
    db = SessionLocal()
    try:
        # This system is meant to have exactly ONE global admin. So the
        # real check isn't "does this email exist" (that only blocks an
        # exact re-run) - it's "does ANY admin already exist" (that blocks
        # ever creating a second one, regardless of which email is used).
        existing_admin = db.query(User).filter(User.global_role == GlobalRole.admin).first()
        if existing_admin:
            print(
                f"An admin already exists: {existing_admin.email} (id={existing_admin.id}). "
                "Refusing to create another. Exiting."
            )
            # Non-zero exit code so this failure is visible to scripts/CI,
            # not just to a human reading stdout.
            sys.exit(1)
        # Still worth guarding the email uniqueness too - the DB column
        # is unique=True, so a clashing email would raise an IntegrityError
        # instead of this clean message.
        existing_email = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing_email:
            print(f"A user with email {ADMIN_EMAIL} already exists (role={existing_email.global_role}). Exiting.")
            sys.exit(1)
        # Build the admin record. Password is hashed the same way the
        # register endpoint hashes it, so normal login still works.
        admin = User(
            name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            global_role=GlobalRole.admin,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"Created admin user: {admin.email} (id={admin.id})")
    finally:
        # Always close the session, even if something above raised.
        db.close()

if __name__ == "__main__":
    create_first_admin()