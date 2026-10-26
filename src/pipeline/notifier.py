import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import get, get_env

logger = logging.getLogger(__name__)


def send_email(title: str, html_content: str, text_content: str | None = None) -> bool:
    if not get("notification.email.enabled", True):
        logger.info("Email notification disabled in config")
        return False

    password = get_env("SMTP_PASSWORD")
    if not password:
        logger.warning("SMTP_PASSWORD not set, skipping email notification")
        return False

    sender = str(get("user.email", "")).strip()
    recipient = str(get("notification.email.to", "") or "").strip() or sender
    smtp_host = get("notification.email.smtp_host", "smtp.gmail.com")
    smtp_port = get("notification.email.smtp_port", 587)
    use_ssl = get("notification.email.use_ssl", smtp_port == 465)

    if not sender:
        logger.warning("User email not configured, skipping email notification")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = sender
        msg["To"] = recipient
        if text_content:
            msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_cls(smtp_host, smtp_port, timeout=get("notification.email.timeout", 15)) as server:
            if not use_ssl:
                server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())

        logger.info("Email notification sent to %s", recipient)
        return True
    except Exception:
        logger.exception("Failed to send email notification")
        return False


def send_report(title: str, html_content: str, text_content: str | None = None) -> dict[str, bool]:
    result = send_email(title, html_content, text_content)
    return {"email": result}
