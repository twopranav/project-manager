from tests import factories


# ---------------------------------------------------------------------------
# /admin/alerts
# ---------------------------------------------------------------------------
def test_non_admin_cannot_view_security_alerts(client, user):
    resp = client.get("/admin/alerts", headers=user["headers"])
    assert resp.status_code == 403


def test_admin_sees_unauthorized_role_change_attempts(client, admin, user, second_user):
    # Trigger an alert: a non-admin tries to change someone's global role.
    client.patch(f"/users/{second_user['id']}/role", json={"global_role": "member"}, headers=user["headers"])

    resp = client.get("/admin/alerts", headers=admin["headers"])
    assert resp.status_code == 200
    alerts = resp.json()
    assert len(alerts) >= 1
    assert all(a["resolved"] is False for a in alerts)


def test_alerts_default_to_unresolved_only(client, admin, user, second_user):
    client.patch(f"/users/{second_user['id']}/role", json={"global_role": "member"}, headers=user["headers"])
    alert_id = client.get("/admin/alerts", headers=admin["headers"]).json()[0]["id"]

    resolve = client.patch(f"/admin/alerts/{alert_id}/resolve", headers=admin["headers"])
    assert resolve.status_code == 200
    assert resolve.json()["resolved"] is True

    default_view = client.get("/admin/alerts", headers=admin["headers"]).json()
    assert alert_id not in [a["id"] for a in default_view]

    full_view = client.get("/admin/alerts", params={"include_resolved": True}, headers=admin["headers"]).json()
    assert alert_id in [a["id"] for a in full_view]


def test_resolving_unknown_alert_is_404(client, admin):
    resp = client.patch("/admin/alerts/does-not-exist/resolve", headers=admin["headers"])
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /admin/transfer-admin
# ---------------------------------------------------------------------------
def test_non_admin_cannot_transfer_admin(client, user, second_user):
    resp = client.post(
        "/admin/transfer-admin",
        json={"new_admin_user_id": second_user["id"]},
        headers=user["headers"],
    )
    assert resp.status_code == 403


def test_non_admin_transfer_attempt_is_logged(client, admin, user, second_user):
    before = client.get("/admin/alerts", headers=admin["headers"]).json()
    client.post("/admin/transfer-admin", json={"new_admin_user_id": second_user["id"]}, headers=user["headers"])
    after = client.get("/admin/alerts", headers=admin["headers"]).json()
    assert len(after) == len(before) + 1


def test_admin_can_transfer_to_another_user(client, admin, user):
    resp = client.post("/admin/transfer-admin", json={"new_admin_user_id": user["id"]}, headers=admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["global_role"] == "admin"

    # The old admin should now be a plain member and lose admin-only access.
    old_admin_check = client.get("/admin/alerts", headers=admin["headers"])
    assert old_admin_check.status_code == 403

    # The new admin should have it.
    new_admin_check = client.get("/admin/alerts", headers=user["headers"])
    assert new_admin_check.status_code == 200


def test_transfer_to_nonexistent_user_is_404(client, admin):
    resp = client.post("/admin/transfer-admin", json={"new_admin_user_id": "does-not-exist"}, headers=admin["headers"])
    assert resp.status_code == 404


def test_transfer_to_self_is_rejected(client, admin):
    resp = client.post("/admin/transfer-admin", json={"new_admin_user_id": admin["id"]}, headers=admin["headers"])
    assert resp.status_code == 400



def test_successful_admin_transfer_is_logged(client, admin, user):
    resp = client.post("/admin/transfer-admin", json={"new_admin_user_id": user["id"]}, headers=admin["headers"])
    assert resp.status_code == 200

    # The new admin is the only one who can view alerts now.
    alerts = client.get("/admin/alerts", headers=user["headers"]).json()
    transfer_alerts = [a for a in alerts if a["alert_type"] == "admin_transfer_success"]
    assert len(transfer_alerts) == 1
    assert transfer_alerts[0]["target_user_id"] == user["id"]