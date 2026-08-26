import pytest

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


def test_manager_cannot_grant_the_admin_tier(client, user, project, second_user, third_user):
    """A manager can add ordinary members but granting project-admin is
    reserved for an existing project admin or the site admin."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "manager")
    resp = factories.add_member_raw(client, second_user["headers"], project["id"], third_user["id"], "admin")
    assert resp.status_code == 403


def test_project_admin_can_grant_the_admin_tier(client, user, project, second_user):
    membership = factories.add_member(client, user["headers"], project["id"], second_user["id"], "admin")
    assert membership["project_role"] == "admin"


def test_site_admin_can_grant_the_admin_tier(client, admin, user, project, second_user):
    """Site admin bypasses membership entirely (see require_project_role),
    so it can add members to a project it doesn't belong to."""
    resp = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": second_user["id"], "project_role": "admin"},
        headers=admin["headers"],
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# update role
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


def test_manager_cannot_promote_someone_to_admin(client, user, project, second_user, third_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "manager")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "viewer")
    resp = client.patch(
        f"/projects/{project['id']}/members/{third_user['id']}",
        json={"project_role": "admin"},
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_cannot_demote_the_last_admin(client, user, project):
    """`user` is the sole (creator) admin of `project`."""
    resp = client.patch(
        f"/projects/{project['id']}/members/{user['id']}",
        json={"project_role": "manager"},
        headers=user["headers"],
    )
    assert resp.status_code == 400


def test_can_demote_an_admin_when_another_admin_remains(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "admin")
    resp = client.patch(
        f"/projects/{project['id']}/members/{user['id']}",
        json={"project_role": "manager"},
        headers=second_user["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["project_role"] == "manager"


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


def test_cannot_remove_the_last_admin(client, user, project):
    resp = client.delete(f"/projects/{project['id']}/members/{user['id']}", headers=user["headers"])
    assert resp.status_code == 400


def test_removing_an_admin_requires_admin_tier_authorization(client, user, project, second_user, third_user):
    """second_user is a manager (not admin), third_user is a project admin
    alongside `user`. A manager may not remove an admin even though the
    project would still have `user` left as admin afterwards."""
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "manager")
    factories.add_member(client, user["headers"], project["id"], third_user["id"], "admin")

    resp = client.delete(
        f"/projects/{project['id']}/members/{third_user['id']}",
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_member_can_leave_a_project_without_manager_rank(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    resp = client.delete(f"/projects/{project['id']}/leave", headers=second_user["headers"])
    assert resp.status_code == 204


def test_last_admin_cannot_leave(client, user, project):
    resp = client.delete(f"/projects/{project['id']}/leave", headers=user["headers"])
    assert resp.status_code == 400


def test_non_member_cannot_leave_a_project(client, project, second_user):
    resp = client.delete(f"/projects/{project['id']}/leave", headers=second_user["headers"])
    assert resp.status_code == 404
