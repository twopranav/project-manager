"""
Integration tests for the alert-dispatch pipeline: POST /alerts/dispatch ->
Celery task -> send_alert_email() -> smtplib.

Unlike tests/test_email.py (which calls send_alert_email() directly),
these tests go through the *actual* Celery task and the *actual* HTTP
route, with Celery set to run tasks synchronously in-process
(`task_always_eager`) instead of needing a real broker/worker. This is
the path that a mocked `.delay()` call would never exercise -- and it's
exactly the path that silently swallowed a real bug during manual testing
(see test_dispatch_reports_success_even_when_smtp_login_fails below).

Only smtplib.SMTP is mocked here -- Celery, the route, and send_alert_email()
all run for real. No external mail server needed.
"""
from unittest.mock import MagicMock

import pytest

from app.core import email as email_module
from app.core.celery_app import celery_app
from tests import factories


@pytest.fixture()
def celery_eager():
    """Run Celery tasks synchronously in-process for the duration of a test,
    instead of queuing them to a real broker for a worker to pick up later.
    Also stores eager results in the backend (off by default) so that
    AsyncResult(task_id) -- what GET /alerts/dispatch/{task_id} uses --
    actually finds something instead of reporting PENDING forever.
    Restores all previous settings afterward so this doesn't leak into
    other tests."""
    prev_eager = celery_app.conf.task_always_eager
    prev_propagates = celery_app.conf.task_eager_propagates
    prev_store_eager = celery_app.conf.task_store_eager_result
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.task_store_eager_result = True
    yield
    celery_app.conf.task_always_eager = prev_eager
    celery_app.conf.task_eager_propagates = prev_propagates
    celery_app.conf.task_store_eager_result = prev_store_eager


@pytest.fixture()
def configured_smtp(monkeypatch):
    """Point send_alert_email() at a fake-but-'configured' SMTP server and
    swap smtplib.SMTP for a mock. Returns (smtp_mock, server_mock) so a
    test can assert on what was called."""
    monkeypatch.setattr(email_module.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_module.settings, "SMTP_PORT", 2525)
    monkeypatch.setattr(email_module.settings, "SMTP_USERNAME", "user")
    monkeypatch.setattr(email_module.settings, "SMTP_PASSWORD", "pass")
    monkeypatch.setattr(email_module.settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_module.settings, "SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setattr(email_module.settings, "ALERT_ADMIN_EMAIL", "admin@example.com")

    server_mock = MagicMock()
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = server_mock
    smtp_mock = MagicMock(return_value=smtp_cm)
    monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_mock)

    return smtp_mock, server_mock


def test_dispatch_endpoint_actually_sends_through_the_real_pipeline(
    client, user, celery_eager, configured_smtp
):
    """POST /alerts/dispatch should, end-to-end, result in a real call to
    smtplib.SMTP -- not just a queued-and-forgotten task. This is the test
    that a mocked send_alert_email_task.delay() could never provide."""
    smtp_mock, server_mock = configured_smtp

    resp = client.post(
        "/alerts/dispatch",
        json={"subject": "Integration Test Alert", "body": "hello from pytest"},
        headers=user["headers"],
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    status_resp = client.get(f"/alerts/dispatch/{task_id}", headers=user["headers"])
    assert status_resp.json()["status"] == "SUCCESS"

    smtp_mock.assert_called_once_with("smtp.example.com", 2525, timeout=10)
    server_mock.starttls.assert_called_once()
    server_mock.login.assert_called_once_with("user", "pass")
    server_mock.send_message.assert_called_once()


def test_dispatch_reports_success_even_when_smtp_login_fails(
    client, user, celery_eager, configured_smtp
):
    """
    Characterization test for the exact bug found during manual testing:
    send_alert_email() swallows ALL SMTP exceptions (including auth
    failures) and never re-raises, so the Celery task -- and therefore the
    /alerts/dispatch/{task_id} endpoint -- reports SUCCESS even though no
    email was actually delivered.

    This test documents that this is current, deliberate behavior (see the
    docstring on send_alert_email: "a mail-server hiccup should not break
    the request that triggered the alert"). It is NOT a claim that this is
    ideal -- silently-successful failures are exactly what caused the
    Mailtrap/Mailpit confusion during manual testing. If that tradeoff ever
    changes (e.g. surfacing failures via a separate status field), this
    test should be updated to match the new contract.
    """
    smtp_mock, server_mock = configured_smtp
    import smtplib as real_smtplib

    server_mock.login.side_effect = real_smtplib.SMTPNotSupportedError(
        "SMTP AUTH extension not supported by server."
    )

    resp = client.post(
        "/alerts/dispatch",
        json={"subject": "Will silently fail", "body": "auth not supported"},
        headers=user["headers"],
    )
    task_id = resp.json()["task_id"]

    status_resp = client.get(f"/alerts/dispatch/{task_id}", headers=user["headers"])
    # Celery/the route report success...
    assert status_resp.json()["status"] == "SUCCESS"

    # ...even though login blew up and the message was never actually sent.
    server_mock.login.assert_called_once()
    server_mock.send_message.assert_not_called()


def test_repeated_403_alert_actually_attempts_an_smtp_send(
    client, admin, user, second_user, celery_eager, configured_smtp
):
    """The repeated_403 auto-trigger (app/core/security_alerts.py) queues
    its email via send_alert_email_task.delay(), same as the manual
    /alerts/dispatch route. With Celery running eagerly, 5 denials in a
    row should result in a real attempted SMTP send, not just a DB row."""
    smtp_mock, server_mock = configured_smtp
    project = factories.create_project(client, user["headers"])

    for _ in range(5):
        resp = client.get(f"/projects/{project['id']}", headers=second_user["headers"])
        assert resp.status_code == 403

    alerts = client.get("/admin/alerts", headers=admin["headers"]).json()
    repeated = [a for a in alerts if a["alert_type"] == "repeated_403"]
    assert len(repeated) == 1

    server_mock.send_message.assert_called_once()