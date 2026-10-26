import smtplib
from email import message_from_string
from unittest.mock import MagicMock, patch

import pytest

import src.pipeline.notifier as notifier
import src.config


@pytest.mark.unit
class TestSendEmail:
    def test_disabled_in_config(self, temp_config_dir, mock_env):
        src.config.reload()
        src.config.set("notification.email.enabled", False)
        result = notifier.send_email("title", "content")
        assert result is False

    def test_no_password(self, temp_config_dir, monkeypatch):
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        result = notifier.send_email("title", "content")
        assert result is False

    def test_no_sender_email(self, temp_config_dir, mock_env, monkeypatch):
        src.config.reload()
        src.config.set("user.email", "")
        result = notifier.send_email("title", "content")
        assert result is False

    def test_successful_send(self, temp_config_dir, mock_env):
        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_server

        with patch("src.pipeline.notifier.smtplib.SMTP", return_value=mock_smtp):
            result = notifier.send_email("Test Subject", "<p>content</p>")
            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once()
            mock_server.sendmail.assert_called_once()

    def test_sends_to_configured_recipient(self, temp_config_dir, mock_env):
        src.config.reload()
        src.config.set("notification.email.to", "digest@example.com")

        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_server

        with patch("src.pipeline.notifier.smtplib.SMTP", return_value=mock_smtp):
            result = notifier.send_email("Test Subject", "<p>content</p>")

        assert result is True
        args = mock_server.sendmail.call_args.args
        assert args[0] == "test@example.com"
        assert args[1] == "digest@example.com"
        assert "To: digest@example.com" in args[2]

    def test_uses_smtp_ssl_for_port_465(self, temp_config_dir, mock_env):
        src.config.reload()
        src.config.set("notification.email.smtp_port", 465)

        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_server

        with patch("src.pipeline.notifier.smtplib.SMTP_SSL", return_value=mock_smtp) as mock_ssl:
            result = notifier.send_email("Test Subject", "<p>content</p>")

        assert result is True
        mock_ssl.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()
        mock_server.starttls.assert_not_called()

    def test_plain_text_part(self, temp_config_dir, mock_env):
        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_server

        with patch("src.pipeline.notifier.smtplib.SMTP", return_value=mock_smtp):
            assert notifier.send_email("title", "<p>html</p>", "plain body") is True

        message = mock_server.sendmail.call_args.args[2]
        parsed = message_from_string(message)
        plain_parts = [
            part.get_payload(decode=True).decode()
            for part in parsed.walk()
            if part.get_content_type() == "text/plain"
        ]
        assert plain_parts == ["plain body"]

    def test_smtp_error(self, temp_config_dir, mock_env):
        with patch("src.pipeline.notifier.smtplib.SMTP", side_effect=smtplib.SMTPException("error")):
            result = notifier.send_email("title", "content")
            assert result is False


@pytest.mark.unit
class TestSendReport:
    def test_send_report(self, temp_config_dir, mock_env):
        with patch("src.pipeline.notifier.send_email", return_value=True):
            results = notifier.send_report("title", "<p>html</p>")
            assert results["email"] is True
