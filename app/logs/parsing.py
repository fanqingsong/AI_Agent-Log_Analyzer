"""Log parsing, formatting and notification helpers for the logs service."""

import logging
import re
import smtplib
import ssl
import time
import uuid
from datetime import datetime
from email.message import EmailMessage

from pydantic import ValidationError

from app.config import (
    EMAIL_NOTIFY_TO,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_USE_TLS,
)
from app.logs.schemas import MockKafkaLogEntry

logger = logging.getLogger(__name__)


def log_to_json(log: str) -> dict:
    """Validate a raw log line and return a structured dict.

    Returns ``{'valid_log': {...}}`` on success or ``{'invalid_log': raw}``
    when parsing/validation fails.
    """
    pattern = r"^\[(.*?)\] (\w+)(?: \[(.*?)\])? (.*?)(?: \((.*?)\))?$"
    match = re.match(pattern, log)

    if not match:
        return {'invalid_log': log}

    timestamp_str, level, component, message, source = match.groups()

    try:
        json_log = {
            "timestamp": datetime.strptime(
                timestamp_str, "%Y-%m-%d %H:%M:%S,%f"
            ).isoformat(),
            "level": level,
            "component": component,
            "message": message,
            "source": source,
        }
        MockKafkaLogEntry(**json_log)
        return {'valid_log': json_log}

    except (ValueError, ValidationError):
        return {'invalid_log': log}

    except Exception as e:
        print("TROUBLE WHILE PARSING: ", log)
        raise RuntimeError(f"Unexpected error in log parsing: {str(e)}") from e


def send_email(message: str, subject: str = "AI Agent for Log Analysis — Alert") -> None:
    """Send an alert email via SMTP.

    Reads SMTP connection details from configuration (see ``app.config``).
    Logs a warning instead of raising if the server is unreachable, so that
    alert failures never break the log-analysis pipeline.
    """
    if not SMTP_HOST:
        logger.warning("SMTP_HOST is not configured; skipping email alert.")
        return

    recipients = EMAIL_NOTIFY_TO.strip()
    if not recipients:
        logger.warning("EMAIL_NOTIFY_TO is not configured; skipping email alert.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = recipients
    msg.set_content(message)

    try:
        context = ssl.create_default_context() if SMTP_USE_TLS else None
        if SMTP_PORT == 465 and SMTP_USE_TLS:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=10)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            if SMTP_USE_TLS:
                server.starttls(context=context)

        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)

        server.send_message(msg)
        server.quit()
    except Exception as e:
        logger.warning("Failed to send email alert: %s", e)


def format_trigger_log(trigger_log: dict) -> str:
    """Format a log dict into a human-readable prompt string for the LLM."""
    
    warning_level = trigger_log['level']
    signal_icon = "🔥" if warning_level == "ERROR" else "⚠️"

    return f"""
    Provided log message:

    **🕒 Timestamp**: {trigger_log['timestamp']}
    **{signal_icon} Level**: {trigger_log['level']}
    **💬 Message**: {trigger_log['component']} {trigger_log['message']} {trigger_log['source']}
    """


def generate_chat_id() -> str:
    """Generate a unique chat ID: ``chat-<millis>-<7-hex>``."""
    timestamp = int(time.time() * 1000)
    rand_part = uuid.uuid4().hex[:7]
    return f"chat-{timestamp}-{rand_part}"
