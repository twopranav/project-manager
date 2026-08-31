from tests import factories
# ---------------------------------------------------------------------------
# /users/me
# ---------------------------------------------------------------------------
def test_get_my_profile_returns_self(client, user):
    resp = client.get("/users/me", headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["email"] == user["email"]


def test_update_my_name(client, user):
    resp = client.patch("/users/me", json={"name": "New Name"}, headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_update_my_password_lets_me_log_in_with_the_new_one(client, user):
    resp = client.patch("/users/me", json={"password": "brand-new-password-1"}, headers=user["headers"])
    assert resp.status_code == 200

    old_login = client.post("/auth/login", data={"username": user["email"], "password": user["password"]})
    assert old_login.status_code == 401

    new_login = client.post("/auth/login", data={"username": user["email"], "password": "brand-new-password-1"})
    assert new_login.status_code == 200


def test_empty_name_update_does_not_blank_out_the_name(client, user):
    """UserUpdate treats "" the same as omitted for both fields (see the
    `if update_data["name"]:` truthiness check in users.py) -- an empty
    string should not overwrite the existing value."""
    resp = client.patch("/users/me", json={"name": ""}, headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["name"] == user["name"]


# ---------------------------------------------------------------------------
# /users/lookup
# ---------------------------------------------------------------------------
def test_plain_member_cannot_look_up_users(client, user, second_user):
    resp = client.get("/users/lookup", params={"email": second_user["email"]}, headers=user["headers"])
    assert resp.status_code == 403


def test_site_admin_can_look_up_any_user(client, admin, user):
    resp = client.get("/users/lookup", params={"email": user["email"]}, headers=admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["id"] == user["id"]


def test_project_manager_can_look_up_users(client, user, project):
    # `user` owns `project` and is therefore its manager, lookup should be allowed.
    resp = client.get("/users/lookup", params={"email": user["email"]}, headers=user["headers"])
    assert resp.status_code == 200


def test_lookup_of_unknown_email_is_404(client, admin):
    resp = client.get("/users/lookup", params={"email": factories.unique_email("ghost")}, headers=admin["headers"])
    assert resp.status_code == 404

# ---------------------------------------------------------------------------
# PATCH /users/{id}/role
# ---------------------------------------------------------------------------
def test_non_admin_cannot_change_global_roles(client, user, second_user):
    resp = client.patch(
        f"/users/{second_user['id']}/role",
        json={"global_role": "member"},
        headers=user["headers"],
    )
    assert resp.status_code == 403


def test_non_admin_role_change_attempt_is_logged_as_a_security_alert(client, admin, user, second_user):
    before = client.get("/admin/alerts", headers=admin["headers"]).json()

    resp = client.patch(
        f"/users/{second_user['id']}/role",
        json={"global_role": "member"},
        headers=user["headers"],
    )
    assert resp.status_code == 403

    after = client.get("/admin/alerts", headers=admin["headers"]).json()
    assert len(after) == len(before) + 1
    assert after[0]["alert_type"] == "unauthorized_global_role_change"
    assert user["id"] in after[0]["message"]


def test_admin_cannot_grant_admin_via_role_endpoint(client, admin, user):
    """Granting admin is only allowed through POST /admin/transfer-admin,
    which demotes the current admin atomically -- this endpoint has no such
    safeguard and should refuse rather than risk two admins."""
    resp = client.patch(f"/users/{user['id']}/role", json={"global_role": "admin"}, headers=admin["headers"])
    assert resp.status_code == 400


def test_admin_can_change_a_members_role(client, admin, user):
    resp = client.patch(f"/users/{user['id']}/role", json={"global_role": "member"}, headers=admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["global_role"] == "member"


def test_role_change_on_unknown_user_is_404(client, admin):
    resp = client.patch("/users/nonexistent-id/role", json={"global_role": "member"}, headers=admin["headers"])
    assert resp.status_code == 404


def test_sole_admin_cannot_demote_themselves(client, admin):
    resp = client.patch(f"/users/{admin['id']}/role", json={"global_role": "member"}, headers=admin["headers"])
    assert resp.status_code == 400
