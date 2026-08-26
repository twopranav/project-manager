from tests import factories


def test_contributor_can_assign_a_project_member(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = factories.assign_task(client, user["headers"], task["id"], second_user["id"])
    assert resp.status_code == 201


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


def test_unassigning_a_user_who_was_never_assigned_is_404(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = client.delete(f"/tasks/{task['id']}/assign/{second_user['id']}", headers=user["headers"])
    assert resp.status_code == 404


def test_assigning_to_a_nonexistent_task_is_404(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = factories.assign_task(client, user["headers"], "does-not-exist", second_user["id"])
    assert resp.status_code == 404
