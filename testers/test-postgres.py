from pathlib import Path
import sys
from uuid import uuid4
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from the project root
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

database_url = os.getenv("DATABASE_URL")

if not database_url:
    print("ERROR: DATABASE_URL was not found in .env")
    sys.exit(1)

print("Connecting to:")
print(database_url)


try:
    engine = create_engine(database_url)

    with engine.connect() as conn:

        # 1. Confirm which PostgreSQL server/database we reached
        result = conn.execute(
            text("SELECT current_database(), current_user, version();")
        ).fetchone()

        print("\nSUCCESS: Connected to PostgreSQL")
        print(f"Database : {result[0]}")
        print(f"User     : {result[1]}")
        print(f"Server   : {result[2].split(',')[0]}")

        # 2. Check that your application's users table exists
        table_check = conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'users'
                );
            """)
        ).scalar()

        print(f"\nusers table exists: {table_check}")

        if not table_check:
            print("ERROR: users table does not exist")
            sys.exit(1)

        # 3. Create a test record directly in PostgreSQL
        test_id = str(uuid4())
        test_email = f"postgres_test_{uuid4().hex[:8]}@example.com"

        conn.execute(
            text("""
                INSERT INTO users (
                    id,
                    name,
                    email,
                    password_hash,
                    global_role
                )
                VALUES (
                    :id,
                    :name,
                    :email,
                    :password_hash,
                    :global_role
                )
            """),
            {
                "id": test_id,
                "name": "PostgreSQL Test User",
                "email": test_email,
                "password_hash": "TEST_ONLY",
                "global_role": "member",
            },
        )

        conn.commit()

        print("\nTEST INSERT SUCCESSFUL")
        print(f"Test ID   : {test_id}")
        print(f"Test email: {test_email}")

        # 4. Read the same record back from PostgreSQL
        inserted = conn.execute(
            text("""
                SELECT id, name, email, global_role
                FROM users
                WHERE id = :id
            """),
            {"id": test_id},
        ).fetchone()

        if not inserted:
            print("\nERROR: Could not read the inserted row back")
            sys.exit(1)

        print("\nTEST READ-BACK SUCCESSFUL")
        print(f"ID    : {inserted[0]}")
        print(f"Name  : {inserted[1]}")
        print(f"Email : {inserted[2]}")
        print(f"Role  : {inserted[3]}")

        print("\nPostgreSQL verification complete.")

except Exception as exc:
    print("\nERROR:")
    print(exc)
    sys.exit(1)