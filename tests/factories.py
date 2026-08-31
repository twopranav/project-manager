"""
Plain helper functions (NOT fixtures) that drive the real HTTP API to set
up test data. Keeping these as functions rather than fixtures means any
test can call `factories.create_task(client, headers, project_id, ...)`
as many times as it needs, with whatever arguments it needs, instead of
being stuck with whatever a fixture happened to produce.

Every "unique_*" helper avoids the DB's unique constraints (project name,
task title within a project, email) colliding across tests -- each call
is stamped with a fresh uuid fragment.

Note on email domains: email-validator (used by Pydantic's EmailStr)
rejects RFC 6761 special-use domains (.test, .example, .invalid,
.localhost) at syntax-validation time. ".dev" is a real, unreserved gTLD,
so it passes. (Carried over from the project's own PowerShell smoke test,
which hit this the hard way.)
"""
import uuid

DEFAULT_PASSWORD = "Str0ngPassword!23"


def unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}.{unique_suffix()}@apiqa.dev"


def unique_name(prefix: str = "Name") -> str:
    return f"{prefix} {unique_suffix()}"


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def register_user(client, name: str = None, email: str = None, password: str = DEFAULT_PASSWORD) -> dict:
    payload = {
        "name": name or unique_name("User"),
        "email": email or unique_email(),
        "password": password,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    body["password"] = password  # register response never echoes it back
    return body


def login(client, email: str, password: str) -> str:
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def register_and_login(client, name: str = None, email: str = None, password: str = DEFAULT_PASSWORD) -> dict:
    user_out = register_user(client, name=name, email=email, password=password)
    token = login(client, user_out["email"], password)
    return {
        "id": user_out["id"],
        "name": user_out["name"],
        "email": user_out["email"],
        "password": password,
        "token": token,
        "headers": auth_headers(token),
    }


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
def create_project(client, headers: dict, name: str = None, description: str = None) -> dict:
    payload = {"name": name or unique_name("Project"), "description": description}
    resp = client.post("/projects/", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_member(client, headers: dict, project_id: str, user_id: str, project_role: str = "contributor") -> dict:
    resp = client.post(
        f"/projects/{project_id}/members",
        json={"user_id": user_id, "project_role": project_role},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_member_raw(client, headers: dict, project_id: str, user_id: str, project_role: str = "contributor"):
    """Same as add_member but returns the raw response, for tests that
    expect the call to fail and want to inspect the status/detail."""
    return client.post(
        f"/projects/{project_id}/members",
        json={"user_id": user_id, "project_role": project_role},
        headers=headers,
    )

def update_member_role(client, headers: dict, project_id: str, user_id: str, project_role: str) -> dict:
    """PATCH a member's project_role -- the only way to promote someone to
    manager (add_member rejects project_role="manager" outright). Asserts
    success; use update_member_role_raw for calls expected to fail."""
    resp = client.patch(
        f"/projects/{project_id}/members/{user_id}",
        json={"project_role": project_role},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def update_member_role_raw(client, headers: dict, project_id: str, user_id: str, project_role: str):
    """Same as update_member_role but returns the raw response, for tests
    that expect the call to fail and want to inspect the status/detail."""
    return client.patch(
        f"/projects/{project_id}/members/{user_id}",
        json={"project_role": project_role},
        headers=headers,
    )

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
def create_task(
    client,
    headers: dict,
    project_id: str,
    title: str = None,
    description: str = None,
    priority: str = "medium",
    due_date: str = None,
) -> dict:
    payload = {
        "project_id": project_id,
        "title": title or unique_name("Task"),
        "description": description,
        "priority": priority,
        "due_date": due_date,
    }
    resp = client.post("/tasks/", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def assign_task(client, headers: dict, task_id: str, user_id: str):
    return client.post(f"/tasks/{task_id}/assign", params={"user_id": user_id}, headers=headers)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
def create_comment(client, headers: dict, task_id: str, content: str = "A comment", parent_comment_id: str = None) -> dict:
    payload = {"task_id": task_id, "content": content, "parent_comment_id": parent_comment_id}
    resp = client.post("/comments/", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Composite helpers for common multi-step setups
# ---------------------------------------------------------------------------
def project_with_member(client, owner_headers: dict, member: dict, project_role: str = "contributor") -> dict:
    """Create a project as the owner and add `member` (a user dict from
    register_and_login) to it with the given role. Returns the project."""
    proj = create_project(client, owner_headers)
    add_member(client, owner_headers, proj["id"], member["id"], project_role)
    return proj
