from tests import factories


def test_contributor_can_comment_on_a_task(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])

    comment = factories.create_comment(client, second_user["headers"], task["id"], content="First!")
    assert comment["content"] == "First!"
    assert comment["user_id"] == second_user["id"]
    assert comment["parent_comment_id"] is None


def test_viewer_cannot_comment(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "viewer")
    task = factories.create_task(client, user["headers"], project["id"])

    resp = client.post(
        "/comments/",
        json={"task_id": task["id"], "content": "sneaky", "parent_comment_id": None},
        headers=second_user["headers"],
    )
    assert resp.status_code == 403


def test_comment_on_nonexistent_task_is_404(client, user):
    resp = client.post(
        "/comments/",
        json={"task_id": "does-not-exist", "content": "hi", "parent_comment_id": None},
        headers=user["headers"],
    )
    assert resp.status_code == 404


def test_reply_to_nonexistent_parent_is_404(client, user, project):
    task = factories.create_task(client, user["headers"], project["id"])
    resp = client.post(
        "/comments/",
        json={"task_id": task["id"], "content": "reply", "parent_comment_id": "does-not-exist"},
        headers=user["headers"],
    )
    assert resp.status_code == 404


def test_reply_whose_parent_belongs_to_a_different_task_is_rejected(client, user, project):
    task_a = factories.create_task(client, user["headers"], project["id"])
    task_b = factories.create_task(client, user["headers"], project["id"])
    parent = factories.create_comment(client, user["headers"], task_a["id"])

    resp = client.post(
        "/comments/",
        json={"task_id": task_b["id"], "content": "cross-task reply", "parent_comment_id": parent["id"]},
        headers=user["headers"],
    )
    assert resp.status_code == 400


def test_comment_tree_nests_replies_under_their_parent(client, user, project):
    task = factories.create_task(client, user["headers"], project["id"])
    root = factories.create_comment(client, user["headers"], task["id"], content="root")
    reply = factories.create_comment(client, user["headers"], task["id"], content="reply", parent_comment_id=root["id"])
    factories.create_comment(client, user["headers"], task["id"], content="reply-to-reply", parent_comment_id=reply["id"])

    tree = client.get(f"/comments/task/{task['id']}", headers=user["headers"]).json()
    assert len(tree) == 1  # exactly one top-level comment
    assert tree[0]["content"] == "root"
    assert len(tree[0]["replies"]) == 1
    assert tree[0]["replies"][0]["content"] == "reply"
    assert tree[0]["replies"][0]["replies"][0]["content"] == "reply-to-reply"


def test_listing_comments_requires_project_membership(client, project, second_user, user):
    task = factories.create_task(client, user["headers"], project["id"])
    resp = client.get(f"/comments/task/{task['id']}", headers=second_user["headers"])
    assert resp.status_code == 403


def test_author_can_edit_their_own_comment(client, user, project):
    task = factories.create_task(client, user["headers"], project["id"])
    comment = factories.create_comment(client, user["headers"], task["id"], content="original")

    resp = client.patch(f"/comments/{comment['id']}", json={"content": "edited"}, headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["content"] == "edited"


def test_other_member_cannot_edit_someone_elses_comment(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    comment = factories.create_comment(client, user["headers"], task["id"])

    resp = client.patch(f"/comments/{comment['id']}", json={"content": "hijacked"}, headers=second_user["headers"])
    assert resp.status_code == 403


def test_site_admin_can_edit_any_comment(client, admin, user, project):
    task = factories.create_task(client, user["headers"], project["id"])
    comment = factories.create_comment(client, user["headers"], task["id"])

    resp = client.patch(f"/comments/{comment['id']}", json={"content": "moderated"}, headers=admin["headers"])
    assert resp.status_code == 200


def test_author_can_delete_their_own_comment(client, user, project):
    task = factories.create_task(client, user["headers"], project["id"])
    comment = factories.create_comment(client, user["headers"], task["id"])

    resp = client.delete(f"/comments/{comment['id']}", headers=user["headers"])
    assert resp.status_code == 204


def test_other_member_cannot_delete_someone_elses_comment(client, user, project, second_user):
    factories.add_member(client, user["headers"], project["id"], second_user["id"], "contributor")
    task = factories.create_task(client, user["headers"], project["id"])
    comment = factories.create_comment(client, user["headers"], task["id"])

    resp = client.delete(f"/comments/{comment['id']}", headers=second_user["headers"])
    assert resp.status_code == 403


def test_edit_of_nonexistent_comment_is_404(client, user):
    resp = client.patch("/comments/does-not-exist", json={"content": "x"}, headers=user["headers"])
    assert resp.status_code == 404
