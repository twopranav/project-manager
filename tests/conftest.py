"""
Shared fixtures for the whole test suite.

Design, in one paragraph: every test gets a FastAPI TestClient whose
`get_db` dependency has been swapped for a SQLAlchemy session that lives
inside a single outer transaction + a SAVEPOINT. The app under test calls
`db.commit()` constantly (that's how the routes are written) — each of
those commits only closes the SAVEPOINT, which we immediately reopen via
an event listener, so nothing the app does ever reaches real disk. After
the test, we roll back the outer transaction and the database is exactly
as it was before the test ran. This means:
  - tests can call real endpoints (register, login, create project...)
    instead of poking the ORM directly, so they exercise the actual code
  - tests never have to clean up after themselves
  - tests can run in any order, and in parallel with pytest-xdist, because
    nothing is shared across test DB transactions

IMPORTANT: this suite talks to a REAL Postgres database (not SQLite),
because the schema uses Postgres-only features (a partial unique index
enforcing a single global admin — see app/models/user.py). Point it at a
throwaway database via TEST_DATABASE_URL; never run it against anything
you care about, since table structure is dropped/recreated each session.
"""
import os
import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Env vars MUST be set before the first `from app...` import anywhere in the
# process, because app.core.config.Settings() reads them at instantiation
# time and app.db.session builds its engine from that at import time.
# ---------------------------------------------------------------------------
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:1234567890@localhost:5432/taskdb_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.db.session import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import GlobalRole, User  # noqa: E402

from tests import factories  # noqa: E402


# ---------------------------------------------------------------------------
# Database lifecycle
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create every table once for the whole run, drop them all at the end.

    Uses Base.metadata directly rather than `alembic upgrade head` — faster,
    and doesn't drift if a migration is written but not yet squashed. If you
    need to test the migrations themselves, do that separately (e.g. a
    single smoke test that runs `alembic upgrade head` against a scratch DB).
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(_schema):
    """One SAVEPOINT-scoped session per test. See module docstring."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = sessionmaker(bind=connection, autoflush=False, autocommit=False)()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    """TestClient wired so every request in this test shares db_session,
    and therefore shares its transaction — nothing survives the test."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User fixtures
#
# `user`, `second_user`, `third_user` are plain registered+logged-in members
# — the common case. `admin` is seeded directly into the DB (mirrors what
# app/scripts/bootstrap_admin.py does in real life, since there is no API
# path that creates an admin — see auth.py) and then logged in for real, so
# its token is a genuine one the app issued.
#
# Each fixture returns a dict: {id, name, email, password, token, headers}
# ---------------------------------------------------------------------------
@pytest.fixture()
def user(client):
    return factories.register_and_login(client)


@pytest.fixture()
def second_user(client):
    return factories.register_and_login(client)


@pytest.fixture()
def third_user(client):
    return factories.register_and_login(client)


@pytest.fixture()
def admin(client, db_session):
    password = "AdminPass!23"
    email = factories.unique_email("admin")
    db_user = User(
        name="Site Admin",
        email=email,
        password_hash=hash_password(password),
        global_role=GlobalRole.admin,
    )
    db_session.add(db_user)
    db_session.commit()
    db_session.refresh(db_user)

    token = factories.login(client, email, password)
    return {
        "id": db_user.id,
        "name": db_user.name,
        "email": email,
        "password": password,
        "token": token,
        "headers": factories.auth_headers(token),
    }


# ---------------------------------------------------------------------------
# Project fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def project(client, user):
    """A project owned by `user`, who is therefore its project-admin."""
    return factories.create_project(client, user["headers"])


@pytest.fixture()
def unique_str():
    """Callable that returns a fresh short unique token, for building
    collision-free names/emails/titles inline in a test body."""
    return lambda prefix="x": f"{prefix}-{uuid.uuid4().hex[:10]}"
