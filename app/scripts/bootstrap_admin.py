"""
One-time, manual bootstrap of the global admin.

This is deliberately NOT an API endpoint. The whole point of this project's
role model is that only the current admin can grant the admin role — which
means there has to be exactly one way to create the *first* admin that
doesn't go through the API at all, since no admin exists yet to authorize it.
That's this script. Run it directly on the machine with DB access; nothing
about it is reachable over the network.

Usage (from the project root, with your venv active and .env configured):

    python -m app.scripts.bootstrap_admin you@example.com

The target user must already exist (register normally first, as a regular
member), then run this once to promote that account. Running it again on an
already-admin account is a harmless no-op.
"""
import sys

from app.db.session import SessionLocal
from app.models.user import User, GlobalRole


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m app.scripts.bootstrap_admin <email>")
        sys.exit(1)

    email = sys.argv[1].strip()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(
                f"No user found with email '{email}'. "
                "Register that account through /auth/register first, then rerun this script."
            )
            sys.exit(1)

        if user.global_role == GlobalRole.admin:
            print(f"'{email}' is already the global admin. Nothing to do.")
            return

        existing_admin = (
            db.query(User)
            .filter(User.global_role == GlobalRole.admin)
            .first()
        )
        if existing_admin is not None:
            print(
                f"An admin already exists: '{existing_admin.email}'. "
                "This script only grants admin when there isn't one yet. "
                "To transfer the role, log in as the current admin and use "
                "PATCH /users/{user_id}/role instead."
            )
            sys.exit(1)

        user.global_role = GlobalRole.admin
        db.commit()
        print(f"'{email}' is now the global admin.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
