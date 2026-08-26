from tests import factories


def test_register_returns_created_user(client):
    email = factories.unique_email("register")
    resp = client.post(
        "/auth/register",
        json={"name": "Ada Lovelace", "email": email, "password": "correct-horse-battery"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == email
    assert body["name"] == "Ada Lovelace"
    assert "password" not in body
    assert "password_hash" not in body


def test_register_new_account_is_always_a_plain_member(client):
    """auth.py deliberately forces global_role=member on every registration
    -- there is no API path to self-elevate to admin. Note this contradicts
    the README ("first user becomes global admin"); this test documents the
    actual, intended behavior so a future doc fix doesn't silently break it."""
    resp = client.post(
        "/auth/register",
        json={"name": "First User", "email": factories.unique_email("first"), "password": "whatever123"},
    )
    assert resp.status_code == 201
    assert resp.json()["global_role"] == "member"


def test_register_duplicate_email_is_rejected(client):
    email = factories.unique_email("dupe")
    first = client.post("/auth/register", json={"name": "A", "email": email, "password": "password123"})
    assert first.status_code == 201

    second = client.post("/auth/register", json={"name": "B", "email": email, "password": "different456"})
    assert second.status_code == 400


def test_login_with_correct_credentials_returns_bearer_token(client):
    reg = factories.register_user(client, password="mypassword123")
    resp = client.post("/auth/login", data={"username": reg["email"], "password": "mypassword123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_with_wrong_password_is_rejected(client):
    reg = factories.register_user(client, password="mypassword123")
    resp = client.post("/auth/login", data={"username": reg["email"], "password": "wrongpassword"})
    assert resp.status_code == 401


def test_login_with_unknown_email_is_rejected(client):
    resp = client.post(
        "/auth/login",
        data={"username": factories.unique_email("nobody"), "password": "irrelevant"},
    )
    assert resp.status_code == 401


def test_login_error_does_not_reveal_which_field_was_wrong(client):
    """Bad email and bad password should be indistinguishable to the
    caller -- both are a generic 401, so login can't be used to enumerate
    registered emails."""
    reg = factories.register_user(client, password="mypassword123")
    bad_password = client.post("/auth/login", data={"username": reg["email"], "password": "nope"})
    bad_email = client.post("/auth/login", data={"username": factories.unique_email(), "password": "nope"})
    assert bad_password.status_code == bad_email.status_code == 401
    assert bad_password.json()["detail"] == bad_email.json()["detail"]


def test_protected_route_without_token_is_rejected(client):
    resp = client.get("/users/me")
    assert resp.status_code == 401


def test_protected_route_with_garbage_token_is_rejected(client):
    resp = client.get("/users/me", headers=factories.auth_headers("not-a-real-jwt"))
    assert resp.status_code == 401
