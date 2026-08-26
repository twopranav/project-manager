from tests import factories


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
def test_create_project_makes_creator_a_project_admin(client, user):
    project = factories.create_project(client, user["headers"])
    resp = client.get(f"/projects/{project['id']}/members", headers=user["headers"])
    assert resp.status_code == 200
    [membership] = [m for m in resp.json() if m["user_id"] == user["id"]]
    assert membership["project_role"] == "admin"


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
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "manager")
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
    """A project manager (not the owner, not the site admin) deleting a
    project is a fully authorized action -- but the site admin should
    still be notified, per spec."""
    project = factories.create_project(client, user["headers"])
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "manager")

    resp = client.delete(f"/projects/{project['id']}", headers=second_user["headers"])
    assert resp.status_code == 204

    alerts = client.get("/admin/alerts", headers=admin["headers"]).json()
    deletion_alerts = [a for a in alerts if a["alert_type"] == "project_deleted"]
    assert len(deletion_alerts) == 1
    assert deletion_alerts[0]["actor_user_id"] == second_user["id"]