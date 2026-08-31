from tests import factories


# ---------------------------------------------------------------------------
# add member
# ---------------------------------------------------------------------------
def test_manager_can_add_a_contributor(client, user, project, second_user):
    membership = factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    assert membership["project_role"] == "contributor"
    assert membership["user_id"] == second_user["id"]


def test_contributor_cannot_add_members(client, user, project, second_user, third_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = factories.add_member_raw(client, second_user["headers"], project["id"], third_user["id"], "viewer")
    assert resp.status_code == 403


def test_adding_duplicate_member_is_rejected(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = factories.add_member_raw(client, user["headers"], project["id"], second_user["id"], "viewer")
    assert resp.status_code == 400


def test_adding_unknown_user_is_404(client, user, project):
    resp = factories.add_member_raw(client, user["headers"], project["id"], "nonexistent-id", "viewer")
    assert resp.status_code == 404


def test_adding_a_member_directly_as_manager_is_rejected(client, user, project, second_user):
    """A project can only ever have one manager -- POST .../members always
    400s on project_role="manager", even for the existing manager, since
    granting it directly could silently create a second manager or clobber
    the current one. PATCH .../members/{user_id} is the only transfer path."""
    resp = factories.add_member_raw(client, user["headers"], project["id"], second_user["id"], "manager")
    assert resp.status_code == 400


def test_site_admin_also_cannot_add_a_manager_directly(client, admin, user, project, second_user):
    """Site admin bypasses membership for require_project_role, but the
    manager-add rejection happens after that check and applies uniformly."""
    resp = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": second_user["id"], "project_role": "manager"},
        headers=admin["headers"],
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# manager transfer via PATCH
# ---------------------------------------------------------------------------
def test_manager_can_promote_a_viewer_to_contributor(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = client.patch(
        f"/projects/{project['id']}/members/{second_user['id']}",
        json={"project_role": "contributor"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["project_role"] == "contributor"


def test_contributor_cannot_promote_anyone(client, user, project, second_user, third_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "viewer")
    resp = client.patch(
        f"/projects/{project['id']}/members/{third_user['id']}",
        json={"project_role": "contributor"},
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_promoting_someone_to_manager_transfers_the_role_and_demotes_the_old_manager(client, user, project, second_user):
    """`user` is the project's manager (creator). Promoting second_user to
    manager via PATCH is a transfer, not a second grant -- the old manager
    should end up as contributor, not still manager."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")

    resp = client.patch(
        f"/projects/{project['id']}/members/{second_user['id']}",
        json={"project_role": "manager"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["project_role"] == "manager"

    members = client.get(f"/projects/{project['id']}/members", headers=user["headers"]).json()
    [old_manager_membership] = [m for m in members if m["user_id"] == user["id"]]
    assert old_manager_membership["project_role"] == "contributor"


def test_update_role_of_non_member_is_404(client, user, project, second_user):
    resp = client.patch(
        f"/projects/{project['id']}/members/{second_user['id']}",
        json={"project_role": "viewer"},
        headers=user["headers"],
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# remove member / leave
# ---------------------------------------------------------------------------
def test_manager_can_remove_a_member(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = client.delete(f"/projects/{project['id']}/members/{second_user['id']}", headers=user["headers"])
    assert resp.status_code == 204

    members = client.get(f"/projects/{project['id']}/members", headers=user["headers"]).json()
    assert second_user["id"] not in [m["user_id"] for m in members]


def test_contributor_cannot_remove_a_member(client, user, project, second_user, third_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "viewer")
    resp = client.delete(
        f"/projects/{project['id']}/members/{third_user['id']}",
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_member_can_leave_a_project_without_manager_rank(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = client.delete(f"/projects/{project['id']}/leave", headers=second_user["headers"])
    assert resp.status_code == 204


def test_non_member_cannot_leave_a_project(client, project, second_user):
    resp = client.delete(f"/projects/{project['id']}/leave", headers=second_user["headers"])
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# manager removal / departure / demotion NEVER blocks -- there is no more
# "cannot remove/demote the last manager" behavior. Instead the site admin
# auto-inherits the manager slot (or the project is simply left without a
# manager if there's no site admin at all).
# ---------------------------------------------------------------------------
def test_removing_the_sole_manager_succeeds_and_site_admin_inherits(client, admin, user, project):
    """`user` is the sole (creator) manager of `project`. Removing them
    used to 400 under the old "last admin" rule -- now it succeeds
    unconditionally, and the site admin gets a membership row as manager."""
    resp = client.delete(f"/projects/{project['id']}/members/{user['id']}", headers=user["headers"])
    assert resp.status_code == 204

    members = client.get(f"/projects/{project['id']}/members", headers=admin["headers"]).json()
    [admin_membership] = [m for m in members if m["user_id"] == admin["id"]]
    assert admin_membership["project_role"] == "manager"


def test_manager_leaving_succeeds_and_site_admin_inherits(client, admin, user, project):
    resp = client.delete(f"/projects/{project['id']}/leave", headers=user["headers"])
    assert resp.status_code == 204

    members = client.get(f"/projects/{project['id']}/members", headers=admin["headers"]).json()
    [admin_membership] = [m for m in members if m["user_id"] == admin["id"]]
    assert admin_membership["project_role"] == "manager"


def test_demoting_the_manager_away_succeeds_and_site_admin_inherits(client, admin, user, project):
    resp = client.patch(
        f"/projects/{project['id']}/members/{user['id']}",
        json={"project_role": "contributor"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["project_role"] == "contributor"

    members = client.get(f"/projects/{project['id']}/members", headers=admin["headers"]).json()
    [admin_membership] = [m for m in members if m["user_id"] == admin["id"]]
    assert admin_membership["project_role"] == "manager"


def test_succession_promotes_an_existing_membership_rather_than_duplicating_it(client, admin, user, project):
    """If the site admin already has a (non-manager) membership row on the
    project when the manager slot opens up, succession should promote that
    existing row in place, not create a second membership for them."""
    factories.add_member(client, user["headers"], project["id"], admin["id"], "viewer")

    resp = client.delete(f"/projects/{project['id']}/members/{user['id']}", headers=user["headers"])
    assert resp.status_code == 204

    members = client.get(f"/projects/{project['id']}/members", headers=admin["headers"]).json()
    admin_memberships = [m for m in members if m["user_id"] == admin["id"]]
    assert len(admin_memberships) == 1
    assert admin_memberships[0]["project_role"] == "manager"


def test_removing_the_sole_manager_with_no_site_admin_leaves_the_project_without_one(client, user, project, second_user):
    """No site admin exists in this test's DB state (the `admin` fixture is
    never requested) -- succession has no one to promote, so the project
    is simply left with zero managers. No error. second_user (a remaining
    contributor) is used to observe the resulting membership list, since
    the removed manager can no longer authenticate a manager-level read."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")

    resp = client.delete(f"/projects/{project['id']}/members/{user['id']}", headers=user["headers"])
    assert resp.status_code == 204

    members = client.get(f"/projects/{project['id']}/members", headers=second_user["headers"]).json()
    assert user["id"] not in [m["user_id"] for m in members]
    assert all(m["project_role"] != "manager" for m in members)


def test_manager_leaving_with_no_site_admin_leaves_the_project_without_one(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")

    resp = client.delete(f"/projects/{project['id']}/leave", headers=user["headers"])
    assert resp.status_code == 204

    members = client.get(f"/projects/{project['id']}/members", headers=second_user["headers"]).json()
    assert all(m["project_role"] != "manager" for m in members)


def test_demoting_the_manager_with_no_site_admin_leaves_the_project_without_one(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")

    resp = client.patch(
        f"/projects/{project['id']}/members/{user['id']}",
        json={"project_role": "viewer"},
        headers=user["headers"],
    )
    assert resp.status_code == 200

    members = client.get(f"/projects/{project['id']}/members", headers=user["headers"]).json()
    assert all(m["project_role"] != "manager" for m in members)


# ---------------------------------------------------------------------------
# global admin bypass -- can manage members on a project it never joined.
# ---------------------------------------------------------------------------
def test_site_admin_can_add_members_to_a_project_it_never_joined(client, admin, user, project, second_user):
    resp = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": second_user["id"], "project_role": "viewer"},
        headers=admin["headers"],
    )
    assert resp.status_code == 201


def test_site_admin_can_remove_members_from_a_project_it_never_joined(client, admin, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    resp = client.delete(f"/projects/{project['id']}/members/{second_user['id']}", headers=admin["headers"])
    assert resp.status_code == 204


def test_site_admin_can_change_member_roles_on_a_project_it_never_joined(client, admin, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = client.patch(
        f"/projects/{project['id']}/members/{second_user['id']}",
        json={"project_role": "contributor"},
        headers=admin["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["project_role"] == "contributor"