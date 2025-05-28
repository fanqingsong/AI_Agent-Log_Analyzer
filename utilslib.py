from datetime import datetime
import re
from schemas import MockKafkaLogEntry
from pydantic import ValidationError

def log_to_json(log: str) -> dict[str, str | dict]:

    pattern = r"^\[(.*?)\] (\w+)(?: \[(.*?)\])? (.*?)(?: \((.*?)\))?$"
    
    match = re.match(pattern, log)

    if not match:
        # Log format is unknown, return as it is
        return {'invalid_log': log}

    timestamp_str, level, component, message, source = match.groups()

    try:
        json_log = {
        "timestamp": datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f"),
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
