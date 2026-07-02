"""Log parsing, formatting and notification helpers for the logs service."""

import re
import time
import uuid
from datetime import datetime

import requests
from pydantic import ValidationError

from app.logs.schemas import MockKafkaLogEntry


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


def send_to_discord(message: str) -> None:
    """Send a message to the project's Discord channel via webhook."""
    webhook_id = 'FzUvToXRdk0WtCqrZhcwIgmEu-R-hoSHQc8eyFsT6OBGX8_n-zPzjNgDouDKocGlNX-w'
    webhook_url = f"https://discord.com/api/webhooks/1377369991803834391/{webhook_id}"
    requests.post(webhook_url, json={"content": message})


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
