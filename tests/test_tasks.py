from tests import factories


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
def test_manager_can_create_a_task(client, user, project):
    """`user` is the project's manager (creator) -- create_task now requires
    manager, bumped up from the old contributor-level requirement."""
    task = factories.create_task(client, user["headers"], project["id"])
    assert task["status"] == "todo"
    assert task["priority"] == "medium"
    assert task["created_by"] == user["id"]


def test_contributor_cannot_create_a_task(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = client.post(
        "/tasks/",
        json={"project_id": project["id"], "title": "Nope", "description": None, "priority": "low", "due_date": None},
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_viewer_cannot_create_a_task(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = client.post(
        "/tasks/",
        json={"project_id": project["id"], "title": "Nope", "description": None, "priority": "low", "due_date": None},
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_duplicate_task_title_within_a_project_is_rejected(client, user, project):
    title = factories.unique_name("Task")
    factories.create_task(client, user["headers"], project["id"], title=title)
    resp = client.post(
        "/tasks/",
        json={"project_id": project["id"], "title": title, "description": None, "priority": "medium", "due_date": None},
        headers=user["headers"],
    )
    assert resp.status_code == 400


def test_same_task_title_is_allowed_in_a_different_project(client, user):
    title = factories.unique_name("Task")
    proj_a = factories.create_project(client, user["headers"])
    proj_b = factories.create_project(client, user["headers"])
    factories.create_task(client, user["headers"], proj_a["id"], title=title)
    resp = client.post(
        "/tasks/",
        json={"project_id": proj_b["id"], "title": title, "description": None, "priority": "medium", "due_date": None},
        headers=user["headers"],
    )
    assert resp.status_code == 201


def test_creating_a_task_writes_an_initial_status_history_entry(client, user, project):
    task = factories.create_task(client, user["headers"], project["id"])
    history = client.get(f"/tasks/{task['id']}/history", headers=user["headers"]).json()
    assert len(history) == 1
    assert history[0]["old_status"] is None
    assert history[0]["new_status"] == "todo"


# ---------------------------------------------------------------------------
# list / filter
# ---------------------------------------------------------------------------
def test_list_tasks_for_project_requires_membership(client, project, second_user):
    resp = client.get(f"/tasks/project/{project['id']}", headers=second_user["headers"])
    assert resp.status_code == 403


def test_list_tasks_filters_by_status_and_priority(client, user, project):
    todo_task = factories.create_task(client, user["headers"], project["id"], priority="high")
    other_task = factories.create_task(client, user["headers"], project["id"], priority="low")
    client.patch(f"/tasks/{other_task['id']}", json={"status": "done"}, headers=user["headers"])

    by_status = client.get(
        f"/tasks/project/{project['id']}", params={"status": "todo"}, headers=user["headers"]
    ).json()
    ids = [t["id"] for t in by_status]
    assert todo_task["id"] in ids and other_task["id"] not in ids

    by_priority = client.get(
        f"/tasks/project/{project['id']}", params={"priority": "high"}, headers=user["headers"]
    ).json()
    ids = [t["id"] for t in by_priority]
    assert todo_task["id"] in ids and other_task["id"] not in ids


def test_list_tasks_filters_by_assignee(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    assigned = factories.create_task(client, user["headers"], project["id"])
    unassigned = factories.create_task(client, user["headers"], project["id"])
    factories.assign_task(client, user["headers"], assigned["id"], second_user["id"])

    resp = client.get(
        f"/tasks/project/{project['id']}", params={"assignee_id": second_user["id"]}, headers=user["headers"]
    ).json()
    ids = [t["id"] for t in resp]
    assert assigned["id"] in ids and unassigned["id"] not in ids


def test_assigned_to_me_only_returns_my_tasks(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    mine = factories.create_task(client, user["headers"], project["id"])
    not_mine = factories.create_task(client, user["headers"], project["id"])
    factories.assign_task(client, user["headers"], mine["id"], second_user["id"])

    resp = client.get("/tasks/assigned/me", headers=second_user["headers"]).json()
    ids = [t["id"] for t in resp]
    assert mine["id"] in ids and not_mine["id"] not in ids


# ---------------------------------------------------------------------------
# update -- field-level role gating
# ---------------------------------------------------------------------------
def test_contributor_can_change_status_only(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = client.patch(f"/tasks/{task['id']}", json={"status": "in_progress"}, headers=second_user["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


def test_contributor_cannot_change_title(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = client.patch(f"/tasks/{task['id']}", json={"title": "Renamed"}, headers=second_user["headers"])
    assert resp.status_code == 403


def test_contributor_cannot_change_status_and_title_together(client, user, project, second_user):
    """Mixed updates are gated by the strictest field in the request --
    status alone is contributor-level, but pairing it with title bumps the
    whole request to manager-level."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = client.patch(
        f"/tasks/{task['id']}",
        json={"status": "in_progress", "title": "Renamed"},
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_manager_can_change_title_and_priority(client, user, project, second_user):
    factories.update_member_role(client, user["headers"], project["id"], second_user["id"], "manager")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = client.patch(
        f"/tasks/{task['id']}",
        json={"title": "Renamed", "priority": "urgent"},
        headers=second_user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"
    assert resp.json()["priority"] == "urgent"


def test_status_change_appends_to_history_but_no_op_update_does_not(client, user, project):
    task = factories.create_task(client, user["headers"], project["id"])

    client.patch(f"/tasks/{task['id']}", json={"description": "just text, no status field"}, headers=user["headers"])
    history_after_non_status_update = client.get(f"/tasks/{task['id']}/history", headers=user["headers"]).json()
    assert len(history_after_non_status_update) == 1  # only the creation entry

    client.patch(f"/tasks/{task['id']}", json={"status": "in_progress"}, headers=user["headers"])
    history_after_status_change = client.get(f"/tasks/{task['id']}/history", headers=user["headers"]).json()
    assert len(history_after_status_change) == 2
    assert history_after_status_change[-1]["old_status"] == "todo"
    assert history_after_status_change[-1]["new_status"] == "in_progress"


def test_renaming_task_to_an_existing_title_in_same_project_is_rejected(client, user, project):
    taken = factories.create_task(client, user["headers"], project["id"])
    mine = factories.create_task(client, user["headers"], project["id"])

    resp = client.patch(f"/tasks/{mine['id']}", json={"title": taken["title"]}, headers=user["headers"])
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
def test_delete_task_cascades_comments_and_assignments(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    factories.assign_task(client, user["headers"], task["id"], second_user["id"])
    factories.create_comment(client, user["headers"], task["id"])

    resp = client.delete(f"/tasks/{task['id']}", headers=user["headers"])
    assert resp.status_code == 204
    assert client.get(f"/tasks/{task['id']}", headers=user["headers"]).status_code == 404


def test_viewer_cannot_delete_a_task(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    task = factories.create_task(client, user["headers"], project["id"])
    resp = client.delete(f"/tasks/{task['id']}", headers=second_user["headers"])
    assert resp.status_code == 403


def test_contributor_cannot_delete_a_task(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    resp = client.delete(f"/tasks/{task['id']}", headers=second_user["headers"])
    assert resp.status_code == 403


def test_get_nonexistent_task_is_404(client, user):
    resp = client.get("/tasks/does-not-exist", headers=user["headers"])
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# global admin bypass -- can manage tasks on a project it never joined.
# ---------------------------------------------------------------------------
def test_site_admin_can_create_and_delete_tasks_on_a_project_it_never_joined(client, admin, user, project):
    resp = client.post(
        "/tasks/",
        json={"project_id": project["id"], "title": "Admin task", "description": None, "priority": "medium", "due_date": None},
        headers=admin["headers"],
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    resp = client.delete(f"/tasks/{task_id}", headers=admin["headers"])
    assert resp.status_code == 204