from app.core import security_alerts as security_alerts_module
from tests import factories

# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
def test_create_project_makes_creator_a_project_manager(client, user):
    project = factories.create_project(client, user["headers"])
    resp = client.get(f"/projects/{project['id']}/members", headers=user["headers"])
    assert resp.status_code == 200
    [membership] = [m for m in resp.json() if m["user_id"] == user["id"]]
    assert membership["project_role"] == "manager"

def test_create_project_with_duplicate_name_is_rejected(client, user):
    name = factories.unique_name("Dup Project")
    first = factories.create_project(client, user["headers"], name=name)
    assert first["name"] == name
    resp = client.post("/projects/", json={"name": name, "description": None}, headers=user["headers"])
    assert resp.status_code == 400

def test_create_project_requires_auth(client):
    resp = client.post("/projects/", json={"name": "No Auth", "description": None})
    assert resp.status_code == 401

# ---------------------------------------------------------------------------
# list / scoping
# ---------------------------------------------------------------------------
def test_list_projects_only_shows_own_projects_to_a_plain_member(client, user, second_user):
    mine = factories.create_project(client, user["headers"])
    factories.create_project(client, second_user["headers"])  # someone else's
    resp = client.get("/projects/", headers=user["headers"])
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert mine["id"] in ids
    assert all(p["owner_id"] == user["id"] or p["id"] == mine["id"] for p in resp.json())

def test_site_admin_sees_every_project_regardless_of_membership(client, admin, user):
    others_project = factories.create_project(client, user["headers"])
    resp = client.get("/projects/", headers=admin["headers"])
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert others_project["id"] in ids

def test_list_projects_filters_by_status(client, user):
    active = factories.create_project(client, user["headers"])
    resp = client.get("/projects/", params={"status": "active"}, headers=user["headers"])
    assert active["id"] in [p["id"] for p in resp.json()]
    resp = client.get("/projects/", params={"status": "archived"}, headers=user["headers"])
    assert active["id"] not in [p["id"] for p in resp.json()]

# ---------------------------------------------------------------------------
# get / update / delete + access control
# ---------------------------------------------------------------------------
def test_non_member_cannot_view_a_project(client, project, second_user):
    resp = client.get(f"/projects/{project['id']}", headers=second_user["headers"])
    assert resp.status_code == 403

def test_member_can_view_a_project_they_belong_to(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = client.get(f"/projects/{project['id']}", headers=second_user["headers"])
    assert resp.status_code == 200

def test_get_nonexistent_project_is_404(client, user):
    resp = client.get("/projects/does-not-exist", headers=user["headers"])
    assert resp.status_code == 404

def test_viewer_cannot_update_project(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = client.patch(f"/projects/{project['id']}", json={"description": "hacked"}, headers=second_user["headers"])
    assert resp.status_code == 403

def test_contributor_cannot_update_project(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = client.patch(f"/projects/{project['id']}", json={"description": "still no"}, headers=second_user["headers"])
    assert resp.status_code == 403

def test_manager_can_update_project(client, user, project, second_user):
    """second_user is promoted to manager via the PATCH transfer endpoint --
    direct add of a manager via POST .../members is rejected (see
    test_project_members.py), so this is the only way to get a second
    manager-capable actor onto the project."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    factories.update_member_role(client, user["headers"], project["id"], second_user["id"], "manager")
    resp = client.patch(f"/projects/{project['id']}", json={"description": "updated"}, headers=second_user["headers"])
    assert resp.status_code == 200
    assert resp.json()["description"] == "updated"

def test_rename_project_to_an_existing_name_is_rejected(client, user):
    taken = factories.create_project(client, user["headers"])
    mine = factories.create_project(client, user["headers"])
    resp = client.patch(f"/projects/{mine['id']}", json={"name": taken["name"]}, headers=user["headers"])
    assert resp.status_code == 400

def test_delete_project_without_tasks_succeeds(client, user):
    project = factories.create_project(client, user["headers"])
    resp = client.delete(f"/projects/{project['id']}", headers=user["headers"])
    assert resp.status_code == 204
    assert client.get(f"/projects/{project['id']}", headers=user["headers"]).status_code == 404

def test_delete_project_with_tasks_is_blocked(client, user, project):
    factories.create_task(client, user["headers"], project["id"])
    resp = client.delete(f"/projects/{project['id']}", headers=user["headers"])
    assert resp.status_code == 400

def test_delete_project_requires_manager(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = client.delete(f"/projects/{project['id']}", headers=second_user["headers"])
    assert resp.status_code == 403

# ---------------------------------------------------------------------------
# global admin bypass -- a site admin can act on a project it has no
# ProjectMember row for at all, like a manager would.
# ---------------------------------------------------------------------------
def test_site_admin_can_view_a_project_it_never_joined(client, admin, user, project):
    resp = client.get(f"/projects/{project['id']}", headers=admin["headers"])
    assert resp.status_code == 200

def test_site_admin_can_update_a_project_it_never_joined(client, admin, user, project):
    resp = client.patch(f"/projects/{project['id']}", json={"description": "admin edit"}, headers=admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["description"] == "admin edit"

def test_site_admin_can_delete_a_project_it_never_joined(client, admin, user, project):
    resp = client.delete(f"/projects/{project['id']}", headers=admin["headers"])
    assert resp.status_code == 204
    assert client.get(f"/projects/{project['id']}", headers=user["headers"]).status_code == 404

# ---------------------------------------------------------------------------
# deletion alerts
# ---------------------------------------------------------------------------
def test_project_deletion_is_logged(client, admin, user):
    project = factories.create_project(client, user["headers"])
    resp = client.delete(f"/projects/{project['id']}", headers=user["headers"])
    assert resp.status_code == 204
    alerts = client.get("/admin/alerts", headers=admin["headers"]).json()
    deletion_alerts = [a for a in alerts if a["alert_type"] == "project_deleted"]
    assert len(deletion_alerts) == 1
    assert deletion_alerts[0]["target_id"] == project["id"]
    assert deletion_alerts[0]["actor_user_id"] == user["id"]

def test_project_deletion_by_manager_is_still_logged(client, admin, user, second_user):
    """A project manager (not the creator, not the site admin) deleting a
    project is a fully authorized action -- but the site admin should
    still be notified, per spec. second_user gets there via the PATCH
    transfer endpoint, since POST .../members rejects a direct manager
    add."""
    project = factories.create_project(client, user["headers"])
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    factories.update_member_role(client, user["headers"], project["id"], second_user["id"], "manager")
    resp = client.delete(f"/projects/{project['id']}", headers=second_user["headers"])
    assert resp.status_code == 204
    alerts = client.get("/admin/alerts", headers=admin["headers"]).json()
    deletion_alerts = [a for a in alerts if a["alert_type"] == "project_deleted"]
    assert len(deletion_alerts) == 1
    assert deletion_alerts[0]["actor_user_id"] == second_user["id"]

def test_manager_deleting_their_own_project_does_not_self_notify(client, user, monkeypatch):
    """When the actor deleting the project IS its manager, log_project_deleted
    is called with manager=None (see projects.py) -- no email should fire
    at all, since there's no one else to notify and project_deleted isn't
    in EMAIL_ENABLED_ALERT_TYPES on its own."""
    project = factories.create_project(client, user["headers"])
    sent = []
    monkeypatch.setattr(
        security_alerts_module,
        "send_alert_email",
        lambda subject, body, to=None: sent.append({"subject": subject, "body": body, "to": to}),
    )
    resp = client.delete(f"/projects/{project['id']}", headers=user["headers"])
    assert resp.status_code == 204
    assert sent == []

def test_deleting_someone_elses_project_emails_the_manager_not_the_actor(client, admin, user, monkeypatch):
    """The site admin deletes a project it never joined; `user` (the
    project's manager) is not the actor, so they should get a direct
    email notification."""
    project = factories.create_project(client, user["headers"])
    sent = []
    monkeypatch.setattr(
        security_alerts_module,
        "send_alert_email",
        lambda subject, body, to=None: sent.append({"subject": subject, "body": body, "to": to}),
    )
    resp = client.delete(f"/projects/{project['id']}", headers=admin["headers"])
    assert resp.status_code == 204
    manager_emails = [s for s in sent if s["to"] == user["email"]]
    assert len(manager_emails) == 1
    assert project["name"] in manager_emails[0]["subject"]
    # The admin (actor) should not have been emailed as the "manager".
    admin_emails = [s for s in sent if s["to"] == admin["email"]]
    assert admin_emails == []

# ---------------------------------------------------------------------------
# viewer role -- fully read-only, everywhere
# ---------------------------------------------------------------------------
def test_viewer_is_fully_read_only_across_projects_members_and_tasks(client, user, project, second_user, third_user):
    """A viewer can view/list project, member, and task data, but every
    mutating action across all three resource types is a 403."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    viewer_headers = second_user["headers"]
    # --- allowed: read-only access ---
    assert client.get(f"/projects/{project['id']}", headers=viewer_headers).status_code == 200
    assert client.get(f"/projects/{project['id']}/members", headers=viewer_headers).status_code == 200
    assert client.get(f"/projects/{project['id']}/stats", headers=viewer_headers).status_code == 200
    assert client.get(f"/tasks/project/{project['id']}", headers=viewer_headers).status_code == 200
    assert client.get(f"/tasks/{task['id']}", headers=viewer_headers).status_code == 200
    # --- forbidden: every mutating action ---
    assert client.patch(
        f"/projects/{project['id']}", json={"description": "nope"}, headers=viewer_headers
    ).status_code == 403
    assert client.delete(f"/projects/{project['id']}", headers=viewer_headers).status_code == 403
    assert factories.add_member_raw(
        client, viewer_headers, project["id"], third_user["id"], "viewer"
    ).status_code == 403
    assert factories.update_member_role_raw(
        client, viewer_headers, project["id"], third_user["id"], "manager"
    ).status_code == 403
    assert client.delete(
        f"/projects/{project['id']}/members/{third_user['id']}", headers=viewer_headers
    ).status_code == 403
    assert client.post(
        "/tasks/",
        json={"project_id": project["id"], "title": "Nope", "description": None, "priority": "low", "due_date": None},
        headers=viewer_headers,
    ).status_code == 403
    assert client.patch(
        f"/tasks/{task['id']}", json={"status": "in_progress"}, headers=viewer_headers
    ).status_code == 403
    assert client.delete(f"/tasks/{task['id']}", headers=viewer_headers).status_code == 403
    assert factories.assign_task(client, viewer_headers, task["id"], third_user["id"]).status_code == 403