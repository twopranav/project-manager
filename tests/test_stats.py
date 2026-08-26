import datetime as dt

from tests import factories


def test_stats_on_empty_project_are_all_zero(client, user, project):
    resp = client.get(f"/projects/{project['id']}/stats", headers=user["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tasks"] == 0
    assert body["overdue_tasks"] == 0
    assert all(count == 0 for count in body["tasks_by_status"].values())


def test_stats_count_tasks_by_status(client, user, project):
    t1 = factories.create_task(client, user["headers"], project["id"])
    t2 = factories.create_task(client, user["headers"], project["id"])
    t3 = factories.create_task(client, user["headers"], project["id"])
    client.patch(f"/tasks/{t2['id']}", json={"status": "in_progress"}, headers=user["headers"])
    client.patch(f"/tasks/{t3['id']}", json={"status": "done"}, headers=user["headers"])

    stats = client.get(f"/projects/{project['id']}/stats", headers=user["headers"]).json()
    assert stats["total_tasks"] == 3
    assert stats["tasks_by_status"]["todo"] == 1
    assert stats["tasks_by_status"]["in_progress"] == 1
    assert stats["tasks_by_status"]["done"] == 1
    assert stats["tasks_by_status"]["blocked"] == 0


def test_overdue_counts_only_unfinished_past_due_tasks(client, user, project):
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    overdue = factories.create_task(client, user["headers"], project["id"], due_date=yesterday)
    not_overdue_future = factories.create_task(client, user["headers"], project["id"], due_date=tomorrow)
    overdue_but_done = factories.create_task(client, user["headers"], project["id"], due_date=yesterday)
    client.patch(f"/tasks/{overdue_but_done['id']}", json={"status": "done"}, headers=user["headers"])

    stats = client.get(f"/projects/{project['id']}/stats", headers=user["headers"]).json()
    assert stats["overdue_tasks"] == 1  # only `overdue`
    assert stats["total_tasks"] == 3


def test_stats_require_project_membership(client, project, second_user):
    resp = client.get(f"/projects/{project['id']}/stats", headers=second_user["headers"])
    assert resp.status_code == 403


def test_stats_for_nonexistent_project_is_404(client, user):
    resp = client.get("/projects/does-not-exist/stats", headers=user["headers"])
    assert resp.status_code == 404
