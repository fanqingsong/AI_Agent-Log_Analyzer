# REDIS impplement:

# https://chatgpt.com/c/6832ebe4-697c-800f-81ef-7577b19430fb

# Docker:
# in cmd: docker run --name redis-stack -p 6379:6379 redis/redis-stack-server:latest

import redis

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0)

# Zapisz coś z TTL (np. 15 minut = 900 sekund)
r.set("log:example", "vector_string_or_serialized_data", ex=900)

# Odczytaj
value = r.get("log:example")

print("Z Redis:", value.decode() if value else "Brak klucza")
