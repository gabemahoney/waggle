"""Admin email escalation for CMA delivery failures."""

import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def build_escalation_body(
    worker_id: str,
    session_name: str,
    caller_id: str,
    error_type: str,
    status_code: int,
    attempt_count: int,
    first_failure: str,
) -> str:
    """Build admin escalation email body."""
    return (
        f"CMA Delivery Failure\n"
        f"--------------------\n"
        f"Worker ID: {worker_id}\n"
        f"Session Name: {session_name}\n"
        f"Caller ID: {caller_id}\n"
        f"Error Type: {error_type}\n"
        f"Status Code: {status_code}\n"
        f"Attempt Count: {attempt_count}\n"
        f"First Failure: {first_failure}\n"
    )


def send_admin_email(admin_email: str, subject: str, body: str) -> None:
    """Send admin escalation email. If admin_email is empty, log instead."""
    if not admin_email:
        logger.warning("Admin escalation (no email configured): %s\n%s", subject, body)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "waggle@localhost"
    msg["To"] = admin_email
    msg.set_content(body)

    try:
        with smtplib.SMTP("localhost") as smtp:
            smtp.send_message(msg)
        logger.info("Admin email sent to %s: %s", admin_email, subject)
    except Exception as e:
        logger.error("Failed to send admin email to %s: %s", admin_email, e)
