# kafka_producer.py

from kafka import KafkaProducer
import json
from datetime import datetime
import random
import time



producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

log_levels = ['INFO', 'WARNING', 'ERROR']
services = ['auth', 'payment', 'inventory', 'shipping']
hosts = ['host1', 'host2', 'host3']

def generate_log():
    level = random.choice(log_levels)
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "message": f"Simulated {level.lower()} from {random.choice(services)}",
        "service": random.choice(services),
        "host": random.choice(hosts)
    }

if __name__ == "__main__":
    for _ in range(50):  # generate 50 logs
        log_entry = generate_log()
        producer.send('logs', log_entry)
        print(f"Sent: {log_entry}")
        time.sleep(0.5)  # simulate delay between logs
