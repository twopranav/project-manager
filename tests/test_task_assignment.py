from tests import factories


def test_manager_can_assign_a_project_member(client, user, project, second_user):
    """`user` is the project's manager (creator) and is the one making this
    call -- assign_user_to_task now requires manager, bumped up from the
    old contributor-level requirement. second_user is added as a plain
    contributor here only to be a valid assignment target."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = factories.assign_task(client, user["headers"], task["id"], second_user["id"])
    assert resp.status_code == 201


def test_contributor_cannot_assign_a_project_member(client, user, project, second_user, third_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = factories.assign_task(client, second_user["headers"], task["id"], third_user["id"])
    assert resp.status_code == 403


def test_cannot_assign_someone_who_is_not_a_project_member(client, user, project, second_user):
    """second_user exists but was never added to `project`."""
    task = factories.create_task(client, user["headers"], project["id"])
    resp = factories.assign_task(client, user["headers"], task["id"], second_user["id"])
    assert resp.status_code == 400


def test_double_assigning_the_same_user_is_rejected(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    factories.assign_task(client, user["headers"], task["id"], second_user["id"])

    resp = factories.assign_task(client, user["headers"], task["id"], second_user["id"])
    assert resp.status_code == 400


def test_viewer_cannot_assign_tasks(client, user, project, second_user, third_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = factories.assign_task(client, second_user["headers"], task["id"], third_user["id"])
    assert resp.status_code == 403


def test_unassign_removes_the_assignment(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    factories.assign_task(client, user["headers"], task["id"], second_user["id"])

    resp = client.delete(f"/tasks/{task['id']}/assign/{second_user['id']}", headers=user["headers"])
    assert resp.status_code == 204

    my_tasks = client.get("/tasks/assigned/me", headers=second_user["headers"]).json()
    assert task["id"] not in [t["id"] for t in my_tasks]


def test_contributor_cannot_unassign(client, user, project, second_user, third_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    factories.assign_task(client, user["headers"], task["id"], third_user["id"])

    resp = client.delete(f"/tasks/{task['id']}/assign/{third_user['id']}", headers=second_user["headers"])
    assert resp.status_code == 403


def test_unassigning_a_user_who_was_never_assigned_is_404(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = client.delete(f"/tasks/{task['id']}/assign/{second_user['id']}", headers=user["headers"])
    assert resp.status_code == 404


def test_assigning_to_a_nonexistent_task_is_404(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = factories.assign_task(client, user["headers"], "does-not-exist", second_user["id"])
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# global admin bypass -- can assign/unassign on a project it never joined.
# ---------------------------------------------------------------------------
def test_site_admin_can_assign_and_unassign_on_a_project_it_never_joined(client, admin, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = factories.assign_task(client, admin["headers"], task["id"], second_user["id"])
    assert resp.status_code == 201

    resp = client.delete(f"/tasks/{task['id']}/assign/{second_user['id']}", headers=admin["headers"])
    assert resp.status_code == 204