````markdown
# Test suite

A pytest suite covering the API: **109 tests across 8 files**, ~110s locally.

## How it's built

Every **test function** gets its own isolated database transaction and pulls in whatever fixtures it needs from `conftest.py`. Practically, that means:

- Adding a test for a new feature means adding a new, small, independent function — never touching existing tests.
- Tests can run in any order, or in parallel (`pytest -n auto`, needs `pytest-xdist`), because nothing is shared between them.
- A failing test tells you exactly which behavior broke, not which step in a long sequence.

## What it needs

A real **Postgres** instance (not SQLite — the schema uses a Postgres-only partial unique index to enforce a single global admin; see `app/models/user.py`).

Point the suite at a **throwaway database** — its tables are dropped and recreated every run, so never point this at anything you care about.

```bash
# Create a scratch database once
psql -U postgres -c "CREATE DATABASE taskdb_test;"

pip install -r requirements.txt
````

`pytest` and `httpx` (needed for the test client) are listed at the bottom of `requirements.txt` alongside the app's runtime dependencies — no separate dev-requirements file.

## Running

```bash
# Uses postgresql://postgres:postgres@localhost:5432/taskdb_test by default
pytest

# Point at a different test database (e.g. CI, a different host/user)
TEST_DATABASE_URL="postgresql://user:pass@host:5432/taskdb_test" pytest

# Just one area
pytest tests/test_tasks.py

# Stop on first failure, show local vars
pytest -x -l
```

Your real `.env` / dev database is never touched — `tests/conftest.py` overrides `DATABASE_URL` in the process environment before the app is imported, so the app's own engine binds to the test database instead.

## Verifying the suite itself

`tests/check_suite.ps1` (Windows PowerShell) runs a battery of checks on the **suite itself**, not just the app. This is useful after any change to `conftest.py` or `factories.py`, or any time you want to confirm the suite is trustworthy rather than just green.

1. **Baseline** — plain run, should be all green.
2. **Mutation** — pauses so you can temporarily break something real (e.g. flip a guard condition) and confirms the **right** test(s) fail, not zero and not everything, then confirms a revert goes back to green.
3. **Isolation** — checks the test database has no leftover tables after a run (`psql -c "\dt"` should report none found).
4. **Repeatability** — runs twice back-to-back, expects identical results.
5. **Order independence** — reruns with `pytest-randomly` if installed.
6. **Flakiness** — runs three times, expects identical pass/fail each time.

```powershell
.\tests\check_suite.ps1
```

Output streams to the console and is also written to `tests/check_suite_output.txt` (overwritten fresh each run).

## How it's organized

```text
tests/
├── conftest.py                # DB lifecycle + auth/project fixtures
│                              # (client, user, second_user, third_user,
│                              # admin, project, db_session)
├── factories.py               # Plain functions that drive the real API
│                              # to build test data
│                              # (register_and_login, create_project,
│                              # create_task, add_member, ...)
│                              # Call these directly in a test body for
│                              # one-off setups the fixtures don't cover.
├── check_suite.ps1            # Validates the suite itself (see above)
├── test_auth.py
├── test_users.py
├── test_projects.py
├── test_project_members.py
├── test_tasks.py
├── test_task_assignment.py
├── test_comments.py
├── test_admin.py
└── test_stats.py
```

## Adding a test for a new feature

Most of the time you want one of the existing fixtures plus `factories`:

```python
def test_my_new_thing(client, user, project, second_user):
    factories.add_member(
        client,
        user["headers"],
        project["id"],
        second_user["id"],
        "manager",
    )

    resp = client.get(
        f"/projects/{project['id']}/whatever",
        headers=second_user["headers"],
    )

    assert resp.status_code == 200
```

If the feature needs a new kind of setup step (e.g. a new resource type), add a small helper function to `factories.py` next to the existing ones rather than inlining raw `client.post(...)` calls across many tests.

That's what keeps individual test files small and independent as the suite grows.

## What's covered

Every route in every router:

* Auth
* Users
* Projects
* Project members
* Tasks
* Task assignment
* Comments
* Admin

The suite also covers the business rules layered on top, including:

* Role-hierarchy gating (`viewer < contributor < manager < admin`)
* The contributor-may-only-touch-status rule on task `PATCH`
* Last-admin protection on both project- and site-level roles
* Project/task name uniqueness
* Task-status history recording
* Comment tree nesting
* Unauthorized role-change security-alert logging

## What's intentionally not covered yet

* **Alembic migrations** — the suite creates tables directly via `Base.metadata.create_all` for speed. If migration coverage is needed, add a separate, slower test that runs `alembic upgrade head` against a scratch database and diffs the resulting schema.
* **Load/concurrency behavior** — for example, two simultaneous requests racing to become the last-remaining project admin.
* **Static frontend** (`frontend/index.html`) — this suite is API-only.

```
```
