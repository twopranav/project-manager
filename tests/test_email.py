"""
Unit tests for app/core/email.py. These don't need the `client`/`db_session`
fixtures -- send_alert_email talks to SMTP directly, not the app or DB.
"""
from unittest.mock import MagicMock
from app.core import email as email_module


def test_send_alert_email_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(email_module.settings, "SMTP_HOST", None)
    monkeypatch.setattr(email_module.settings, "ALERT_ADMIN_EMAIL", None)

    smtp_mock = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_mock)

    email_module.send_alert_email(subject="test", body="test body")

    smtp_mock.assert_not_called()


def test_send_alert_email_skips_when_no_recipient(monkeypatch):
    monkeypatch.setattr(email_module.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_module.settings, "ALERT_ADMIN_EMAIL", None)

    smtp_mock = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", smtp_mock)

    email_module.send_alert_email(subject="test", body="test body")

    smtp_mock.assert_not_called()


def test_send_alert_email_sends_when_configured(monkeypatch):
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

    email_module.send_alert_email(subject="[Security Alert] test", body="test body")

    smtp_mock.assert_called_once_with("smtp.example.com", 2525, timeout=10)
    server_mock.starttls.assert_called_once()
    server_mock.login.assert_called_once_with("user", "pass")
    server_mock.send_message.assert_called_once()


def test_send_alert_email_swallows_smtp_failure(monkeypatch):
    monkeypatch.setattr(email_module.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_module.settings, "ALERT_ADMIN_EMAIL", "admin@example.com")

    def _raise(*args, **kwargs):
        raise ConnectionRefusedError("no mail server here")

    monkeypatch.setattr(email_module.smtplib, "SMTP", _raise)

    # Should not raise -- a dead mail server must never break the caller.
    email_module.send_alert_email(subject="test", body="test body")