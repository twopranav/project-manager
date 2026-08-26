"""
Tests for the repeated-403 alert logic in app/api/deps.py
(log_access_denied_and_check_repeated). Uses a plain GET on a project the
caller isn't a member of as the cheapest reliable way to trigger a 403
through require_project_role.
"""
from tests import factories


def test_five_denials_triggers_repeated_403_alert(client, admin, user, second_user):
    project = factories.create_project(client, user["headers"])

    # second_user is never added as a member -- every GET is a 403.
    for _ in range(5):
        resp = client.get(f"/projects/{project['id']}", headers=second_user["headers"])
        assert resp.status_code == 403

    alerts = client.get("/admin/alerts", headers=admin["headers"]).json()
    repeated = [a for a in alerts if a["alert_type"] == "repeated_403"]
    assert len(repeated) == 1
    assert repeated[0]["actor_user_id"] == second_user["id"]

    # The individual denials should also be visible, log-only.
    denied = [a for a in alerts if a["alert_type"] == "access_denied"]
    assert len(denied) == 5


def test_fewer_than_threshold_denials_does_not_alert(client, admin, user, second_user):
    project = factories.create_project(client, user["headers"])

    for _ in range(4):
        resp = client.get(f"/projects/{project['id']}", headers=second_user["headers"])
        assert resp.status_code == 403

    alerts = client.get("/admin/alerts", headers=admin["headers"]).json()
    repeated = [a for a in alerts if a["alert_type"] == "repeated_403"]
    assert len(repeated) == 0


def test_repeated_403_does_not_fire_twice_in_cooldown_window(client, admin, user, second_user):
    project = factories.create_project(client, user["headers"])

    # 10 denials in a row should still only produce one repeated_403 alert
    # -- the cooldown check in log_access_denied_and_check_repeated should
    # suppress a second one within the same window.
    for _ in range(10):
        client.get(f"/projects/{project['id']}", headers=second_user["headers"])

    alerts = client.get("/admin/alerts", headers=admin["headers"]).json()
    repeated = [a for a in alerts if a["alert_type"] == "repeated_403"]
    assert len(repeated) == 1

    denied = [a for a in alerts if a["alert_type"] == "access_denied"]
    assert len(denied) == 10