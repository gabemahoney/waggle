"""Tests for waggle/mailer.py."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from waggle.mailer import build_escalation_body, send_admin_email


class TestBuildEscalationBody:
    def test_returns_string(self):
        body = build_escalation_body(
            worker_id="w-1",
            session_name="my-session",
            caller_id="caller-99",
            error_type="CMARetryableError",
            status_code=500,
            attempt_count=7,
            first_failure="2026-01-01T00:00:00",
        )
        assert isinstance(body, str)

    def test_contains_all_fields(self):
        body = build_escalation_body(
            worker_id="w-abc",
            session_name="sess-xyz",
            caller_id="cal-123",
            error_type="CMATerminalError",
            status_code=403,
            attempt_count=3,
            first_failure="2026-04-01T12:00:00",
        )
        assert "w-abc" in body
        assert "sess-xyz" in body
        assert "cal-123" in body
        assert "CMATerminalError" in body
        assert "403" in body
        assert "3" in body
        assert "2026-04-01T12:00:00" in body


class TestSendAdminEmail:
    def test_empty_email_logs_warning_no_smtp(self, caplog):
        with patch("waggle.mailer.smtplib.SMTP") as mock_smtp:
            with caplog.at_level(logging.WARNING, logger="waggle.mailer"):
                send_admin_email("", "Test Subject", "Test body")
            mock_smtp.assert_not_called()
        assert "no email configured" in caplog.text.lower() or "warning" in caplog.text.lower() or caplog.records

    def test_empty_email_logs_warning_message(self, caplog):
        with patch("waggle.mailer.smtplib.SMTP"):
            with caplog.at_level(logging.WARNING, logger="waggle.mailer"):
                send_admin_email("", "Alert Subject", "Some body")
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_valid_email_calls_smtp(self):
        with patch("waggle.mailer.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_instance = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_admin_email("admin@example.com", "Alert", "Body text")
            mock_smtp_cls.assert_called_once_with("localhost")
            mock_smtp_instance.send_message.assert_called_once()

    def test_valid_email_message_fields(self):
        with patch("waggle.mailer.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_instance = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_admin_email("admin@example.com", "My Subject", "My body")
            msg = mock_smtp_instance.send_message.call_args[0][0]
            assert msg["Subject"] == "My Subject"
            assert msg["To"] == "admin@example.com"
            assert msg["From"] == "waggle@localhost"

    def test_smtp_failure_logs_error_does_not_raise(self, caplog):
        with patch("waggle.mailer.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = OSError("connection refused")
            with caplog.at_level(logging.ERROR, logger="waggle.mailer"):
                # Must not raise
                send_admin_email("admin@example.com", "Subject", "Body")
        assert any(r.levelno == logging.ERROR for r in caplog.records)
