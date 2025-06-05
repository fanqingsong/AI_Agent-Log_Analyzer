from datetime import datetime
import re
from schemas import MockKafkaLogEntry
from pydantic import ValidationError
import requests

#===================================================================================================

def log_to_json(log: str) -> dict:
    """Function for log validation"""
    
    pattern = r"^\[(.*?)\] (\w+)(?: \[(.*?)\])? (.*?)(?: \((.*?)\))?$"
    
    match = re.match(pattern, log)

    if not match:
        # Log format is unknown, return as it is
        return {'invalid_log': log}

    timestamp_str, level, component, message, source = match.groups()

    try:
        json_log = {
        "timestamp": datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f").isoformat(),
        "level": level,
        "component": component,
        "message": message, 
        "source": source
        }

        MockKafkaLogEntry(**json_log)
        # try to validate json_log

        return {'valid_log': json_log}

    except (ValueError, ValidationError) as e:
        # Pydantic validation failed
        return {'invalid_log': log}

    except Exception as e:
        # Unexpected errors — raise to let FastAPI handle it (500)
        print("TROUBLE WHILE PARSING: ", log)
        raise RuntimeError(f"Unexpected error in log parsing: {str(e)}") from e

#===================================================================================================
# TO DISCORD CHANEL

def send_to_discord(message):
    """Simple function to sent communication from AI Agent to Discord"""

    # Very long one webhook to Discord
    webhook_id = 'FzUvToXRdk0WtCqrZhcwIgmEu-R-hoSHQc8eyFsT6OBGX8_n-zPzjNgDouDKocGlNX-w'
    webhook_url = f"https://discord.com/api/webhooks/1377369991803834391/{webhook_id}"

    requests.post(webhook_url, json={"content": message})

#===================================================================================================

def format_trigger_log(trigger_log: dict) -> str:
    # To be transfered to utillibs mod (later):

    warning_level = trigger_log['level']

    if warning_level == "ERROR":
        signal_icon: str = "🔥"
    else:
        signal_icon: str = "⚠️"


    log_parsed: str = f"""
    Provided log message:

    **🕒 Timestamp**: {trigger_log['timestamp']}
    **{signal_icon} Level**: {trigger_log['level']}
    **💬 Message**: {trigger_log['component']} {trigger_log['message']} {trigger_log['source']}
    """

    return log_parsed