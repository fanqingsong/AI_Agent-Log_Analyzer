from datetime import datetime
import re
from schemas import MockKafkaLogEntry
from pydantic import ValidationError

def log_to_json(log: str) -> dict[str, MockKafkaLogEntry | str]:

    pattern = r"^\[(.*?)\] (\w+)(?: \[(.*?)\])? (.*?)(?: \((.*?)\))?$"
    
    match = re.match(pattern, log)

    if not match:
        # Log format is unknown, return as it is
        return {'invalid_log': log}

    if match:

        timestamp_str, level, component, message, source = match.groups()
        
        try:
            json_log = {
            "timestamp": datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f"),
            "level": level,
            "component": component,
            "message": message, 
            "source": source
            }

            return {'valid_log': MockKafkaLogEntry(**json_log)}
        
            ## more complicated?:
            # return {'valid_log': MockKafkaLogEntry.model_validate_json(json_log)}
        
        except (ValueError, ValidationError) as e:
            # Pydantic validation failed

            return {'invalid_log': log}

if __name__ == '__main__':
    log1 = "[2025-04-25 22:35:17,516] INFO Registered kafka:type=kafka.Log4jController MBean (kafka.utils.Log4jControllerRegistration$)"
    log2 = 'org.apache.kafka.common.errors.AuthorizerNotReadyException'
    res = log_to_json(log2)
    print(res)
    # print(res['valid_log'].timestamp)


